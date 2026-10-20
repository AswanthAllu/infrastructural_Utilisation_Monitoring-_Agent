import io
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
import paramiko
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)

# Core system processes that must NEVER be terminated by remediation
PROTECTED_PROCESSES = {
    "systemd", "sshd", "init", "kthreadd", "dockerd", "containerd",
    "systemd-journald", "systemd-udevd", "systemd-networkd",
    "dbus-daemon", "cron", "rsyslogd", "bash", "login", "sudo",
    "dashboard.py", "dashboard"
}

AUDIT_LOG_FILE = PROJECT_ROOT / "logs" / "remediation_audit.log"


class SSHRemediationService:
    """
    Secure SSH-based execution service for Human-in-the-Loop (HITL) remediation.
    Connects to the monitored VM to execute approved operations (e.g. kill rogue PID, restart service).
    """

    def __init__(self):
        # Extract host from VM_HOST or fallback from METRICS_API_BASE_URL
        self._load_config()

    def _load_config(self):
        """Dynamically reloads credentials from .env so modifications take effect immediately."""
        load_dotenv(PROJECT_ROOT / ".env", override=True)
        base_api = os.getenv("METRICS_API_BASE_URL", "http://20.15.164.79:8080")
        extracted_ip = re.search(r"https?://([^:/]+)", base_api)
        default_host = extracted_ip.group(1) if extracted_ip else "20.15.164.79"

        self.host = (os.getenv("VM_HOST") or default_host).strip()
        self.port = int((os.getenv("VM_SSH_PORT") or "22").strip())
        self.username = (os.getenv("VM_USER") or os.getenv("VM_SSH_USER") or "azureuser").strip()

        key_env = (os.getenv("VM_KEY_PATH") or os.getenv("VM_SSH_KEY_PATH") or "").strip()
        self.key_path = None
        if key_env:
            candidate = PROJECT_ROOT / key_env if (PROJECT_ROOT / key_env).exists() else Path(key_env)
            if candidate.exists() and candidate.stat().st_size > 0:
                self.key_path = str(candidate)
        else:
            default_key = PROJECT_ROOT / "config" / "vm_key.pem"
            if default_key.exists() and default_key.stat().st_size > 0:
                self.key_path = str(default_key)

        self.key_content = os.getenv("VM_SSH_KEY_CONTENT", None)
        pwd = os.getenv("VM_PASSWORD") or os.getenv("VM_SSH_PASSWORD")
        self.password = pwd.strip() if pwd else None

    def _get_ssh_client(self) -> paramiko.SSHClient:
        """Establishes an authenticated SSH connection to the target VM."""
        self._load_config()
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs: Dict[str, Any] = {
            "hostname": self.host,
            "port": self.port,
            "username": self.username,
            "timeout": 12,
        }

        # 1. Try private key content if valid
        if self.key_content and self.key_content.strip():
            try:
                key_file = io.StringIO(self.key_content.strip())
                try:
                    connect_kwargs["pkey"] = paramiko.RSAKey.from_private_key(key_file)
                except Exception:
                    key_file.seek(0)
                    connect_kwargs["pkey"] = paramiko.Ed25519Key.from_private_key(key_file)
                client.connect(**connect_kwargs)
                return client
            except Exception as e:
                logger.warning(f"SSH private key content failed ({e}), falling back to password...")

        # 2. Try private key file if exists and not empty (> 0 bytes)
        if self.key_path and Path(self.key_path).exists() and Path(self.key_path).stat().st_size > 0:
            try:
                connect_kwargs["key_filename"] = self.key_path
                client.connect(**connect_kwargs)
                return client
            except Exception as e:
                logger.warning(f"SSH key file '{self.key_path}' failed ({e}), falling back to password...")

        # 3. Try password authentication
        if self.password:
            connect_kwargs["password"] = self.password
            client.connect(**connect_kwargs)
            return client

        raise ValueError(
            f"No valid SSH credentials found for {self.username}@{self.host}. "
            f"Please set a valid VM_KEY_PATH (non-empty .pem) or VM_PASSWORD in backend/.env."
        )

    def test_connection(self) -> Dict[str, Any]:
        """Validates SSH connectivity and credentials to the VM."""
        self._load_config()
        res = self._run_ssh_command("uname -a && uptime")
        if res.get("success"):
            return {
                "success": True,
                "host": self.host,
                "username": self.username,
                "output": res.get("stdout", ""),
                "message": "SSH connection established successfully."
            }
        else:
            return {
                "success": False,
                "host": self.host,
                "username": self.username,
                "error": res.get("stderr") or "Non-zero exit code returned",
                "output": res.get("stdout", ""),
                "message": f"SSH connection failed: {res.get('stderr') or 'Unknown error'}"
            }

    def execute_approved_command(
        self,
        command: str,
        operator: str = "operator",
        action_id: Optional[str] = None,
        operator_note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Unified execution function for all approved VM remediation commands decided by LLM.
        Takes the whitespace-separated command string, validates tokens against security
        guardrails, executes on the remote VM via SSH, and records an immutable audit log.
        """
        clean_cmd = command.strip()
        if not clean_cmd:
            raise ValueError("Command cannot be empty.")

        # 1. Injection prevention: disallow command chaining or redirection
        forbidden_chars = [";", "&&", "||", "|", "`", "$(", "${", ">", "<", "\n", "\r"]
        for fc in forbidden_chars:
            if fc in clean_cmd:
                raise ValueError(f"Security Guardrail: Forbidden shell metacharacter '{fc}' in command.")

        # 2. Tokenize by whitespace
        tokens = clean_cmd.split()
        if not tokens:
            raise ValueError("No command tokens found.")

        # Strip 'sudo' prefix if present for binary validation
        exec_tokens = tokens[1:] if tokens[0] == "sudo" else tokens
        if not exec_tokens:
            raise ValueError("Command specifies only 'sudo' without a binary.")

        binary = exec_tokens[0]
        allowed_binaries = {"kill", "pkill", "systemctl", "renice"}
        if binary not in allowed_binaries:
            raise ValueError(
                f"Security Guardrail: Binary '{binary}' is not permitted. "
                f"Allowed remediation binaries: {', '.join(sorted(allowed_binaries))}"
            )

        # 3. Guardrail checks per binary
        action_type = "REMEDIATION"
        target_name = "system"

        if binary in ("kill", "pkill"):
            action_type = "KILL_PROCESS"
            for tok in exec_tokens[1:]:
                if tok.isdigit():
                    pid = int(tok)
                    if pid <= 100:
                        raise ValueError(f"Security Guardrail: Refusing to terminate system PID {pid} (reserved core OS range <= 100).")
                    target_name = f"PID {pid}"
                elif not tok.startswith("-"):
                    if tok.lower() in PROTECTED_PROCESSES:
                        raise ValueError(f"Security Guardrail: Target '{tok}' is a protected core system process.")
                    target_name = tok

        elif binary == "systemctl":
            action_type = "RESTART_SERVICE"
            if len(exec_tokens) >= 3:
                subcmd = exec_tokens[1]
                svc = exec_tokens[2].replace(".service", "")
                if subcmd in ("stop", "kill") and svc.lower() in PROTECTED_PROCESSES:
                    raise ValueError(f"Security Guardrail: Cannot {subcmd} protected core service '{svc}'.")
                if not re.match(r"^[a-zA-Z0-9_\-\.]+$", svc):
                    raise ValueError(f"Security Guardrail: Invalid service name format '{svc}'.")
                target_name = f"Service {svc}"

        elif binary == "renice":
            action_type = "RENICE_PROCESS"
            for i, tok in enumerate(exec_tokens):
                if tok == "-p" and i + 1 < len(exec_tokens) and exec_tokens[i + 1].isdigit():
                    pid = int(exec_tokens[i + 1])
                    if pid <= 100:
                        raise ValueError(f"Security Guardrail: Refusing to renice system PID {pid} (reserved core OS range <= 100).")
                    target_name = f"PID {pid}"

        # 4. Execute over SSH
        res = self._run_ssh_command(clean_cmd)

        # 5. Record audit log with full execution details
        status = "EXECUTED" if res["success"] else "FAILED"
        self._record_audit_log(
            action_id=action_id or f"ACT-LLM-{int(datetime.now(timezone.utc).timestamp())}",
            operator=operator,
            action_type=action_type,
            target=target_name,
            command=clean_cmd,
            success=res["success"],
            output=res.get("stdout") or res.get("stderr") or "",
            decision="APPROVED",
            status=status,
            exit_code=res.get("exit_code"),
            operator_note=operator_note,
            stdout=res.get("stdout", ""),
            stderr=res.get("stderr", "")
        )

        return {
            "success": res["success"],
            "action": action_type,
            "target": target_name,
            "command": clean_cmd,
            "stdout": res["stdout"],
            "stderr": res["stderr"],
            "exit_code": res["exit_code"],
        }

    def execute_approved_kill(
        self,
        pid: int,
        process_name: str = "",
        signal: int = 15,
        operator: str = "operator",
        action_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Unified wrapper for killing a process."""
        signal = signal if signal in (15, 9, 2) else 15
        return self.execute_approved_command(
            command=f"sudo kill -{signal} {pid}",
            operator=operator,
            action_id=action_id or f"ACT-KILL-{pid}"
        )

    def execute_approved_service_restart(
        self,
        service_name: str,
        operator: str = "operator",
        action_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Unified wrapper for restarting a service."""
        clean_service = service_name.strip().replace(".service", "")
        return self.execute_approved_command(
            command=f"sudo systemctl restart {clean_service}",
            operator=operator,
            action_id=action_id or f"ACT-RESTART-{clean_service}"
        )

    def execute_approved_renice(
        self,
        pid: int,
        priority: int = 19,
        process_name: str = "",
        operator: str = "operator",
        action_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Unified wrapper for renicing a process."""
        priority = max(min(int(priority), 19), -20)
        return self.execute_approved_command(
            command=f"sudo renice -n {priority} -p {pid}",
            operator=operator,
            action_id=action_id or f"ACT-RENICE-{pid}"
        )

    def _run_ssh_command(self, cmd: str) -> Dict[str, Any]:
        """Executes a command over SSH and captures stdout/stderr/exit_code."""
        client = None
        try:
            client = self._get_ssh_client()
            logger.info(f"Executing SSH command on {self.host}: {cmd}")
            stdin, stdout, stderr = client.exec_command(cmd, timeout=20)

            out = stdout.read().decode("utf-8", errors="replace").strip()
            err = stderr.read().decode("utf-8", errors="replace").strip()
            exit_code = stdout.channel.recv_exit_status()

            return {
                "success": exit_code == 0,
                "command": cmd,
                "stdout": out,
                "stderr": err,
                "exit_code": exit_code,
            }
        except Exception as exc:
            logger.error(f"SSH execution error on {self.host}: {exc}")
            return {
                "success": False,
                "command": cmd,
                "stdout": "",
                "stderr": str(exc),
                "exit_code": -1,
            }
        finally:
            if client:
                try:
                    client.close()
                except Exception:
                    pass

    def _record_audit_log(
        self,
        action_id: str,
        operator: str,
        action_type: str,
        target: str,
        command: str,
        success: bool,
        output: str,
        decision: Optional[str] = None,
        status: Optional[str] = None,
        exit_code: Optional[int] = None,
        operator_note: Optional[str] = None,
        stdout: Optional[str] = None,
        stderr: Optional[str] = None,
    ):
        """Records an immutable audit entry into logs/remediation_audit.log."""
        try:
            AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            norm_decision = decision or ("APPROVED" if success or command != "N/A (REJECTED_BY_OPERATOR)" else "REJECTED")
            norm_status = status or ("EXECUTED" if success else ("REJECTED" if norm_decision == "REJECTED" else "FAILED"))
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action_id": action_id,
                "operator": operator,
                "action_type": action_type,
                "target": target,
                "command": command,
                "decision": norm_decision,
                "status": norm_status,
                "exit_code": exit_code if exit_code is not None else (0 if success else -1),
                "operator_note": operator_note or "",
                "stdout": stdout or (output if success else ""),
                "stderr": stderr or (output if not success else ""),
                "output": output or "",
            }
            with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as exc:
            logger.warning(f"Could not write to remediation audit log: {exc}")


# Singleton instance
ssh_remediation = SSHRemediationService()

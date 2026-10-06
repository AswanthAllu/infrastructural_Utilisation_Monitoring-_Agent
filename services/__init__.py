def run_support_agent(*args, **kwargs):
    from .agent_service import run_support_agent as _run
    return _run(*args, **kwargs)

__all__ = ["run_support_agent"]
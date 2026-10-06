const fs = require('fs');
const path = require('path');
const nodemailer = require('nodemailer');

const LOGS_DIR = path.resolve(__dirname, '..', 'logs');
const ALERTS_LOG = path.join(LOGS_DIR, 'email_alerts.log');

async function sendMail(payload) {
  const recipient = payload.to || process.env.DEFAULT_ALERT_EMAIL || '';
  const subject = payload.subject || `Limit crossed alert`;
  const htmlContent = payload.html || `<p>${payload.text || 'System resource threshold crossed.'}</p>`;
  const textContent = payload.text || payload.subject;

  const smtpEnabled = (process.env.SMTP_ENABLED || 'false').toLowerCase() === 'true';
  const smtpHost = process.env.SMTP_HOST || 'smtp.gmail.com';
  const smtpPort = parseInt(process.env.SMTP_PORT || '587', 10);
  const smtpUser = process.env.SMTP_USER || '';
  const smtpPass = process.env.SMTP_PASS || '';
  const smtpFrom = process.env.SMTP_FROM || 'system-monitor@agentecosystem.local';

  let sendResult = {
    timestamp: new Date().toISOString(),
    recipient: recipient,
    subject: subject,
    resource: payload.resource || 'UNKNOWN',
    threshold: payload.threshold || null,
    usage_percent: payload.usage_percent || null,
    status: 'RECORDED_LOCALLY',
    provider: 'nodemailer',
    action_taken: `Nodemailer alert registered for ${recipient}`,
  };

  if (smtpEnabled && smtpUser && smtpPass) {
    try {
      const transporter = nodemailer.createTransport({
        host: smtpHost,
        port: smtpPort,
        secure: smtpPort === 465,
        auth: {
          user: smtpUser,
          pass: smtpPass,
        },
      });

      const info = await transporter.sendMail({
        from: smtpFrom,
        to: recipient,
        subject: subject,
        text: textContent,
        html: htmlContent,
      });

      sendResult.status = 'SENT';
      sendResult.messageId = info.messageId;
      sendResult.action_taken = `Email sent successfully via Nodemailer to ${recipient}`;
    } catch (err) {
      sendResult.status = 'SMTP_FAILED_FALLBACK_RECORDED';
      sendResult.error = err.message;
    }
  }

  // Ensure logs directory exists and record entry
  if (!fs.existsSync(LOGS_DIR)) {
    fs.mkdirSync(LOGS_DIR, { recursive: true });
  }
  fs.appendFileSync(ALERTS_LOG, JSON.stringify(sendResult) + '\n', 'utf-8');

  return sendResult;
}

// CLI invocation support: node nodemailer_service.js <base64_or_json>
if (require.main === module) {
  let rawArg = process.argv[2];
  if (rawArg) {
    try {
      if (!rawArg.trim().startsWith('{')) {
        rawArg = Buffer.from(rawArg, 'base64').toString('utf-8');
      }
      const payload = JSON.parse(rawArg);
      sendMail(payload)
        .then((res) => {
          console.log(JSON.stringify(res));
          process.exit(0);
        })
        .catch((err) => {
          console.error(JSON.stringify({ error: err.message }));
          process.exit(1);
        });
    } catch (err) {
      console.error(JSON.stringify({ error: 'Failed to parse payload: ' + err.message }));
      process.exit(1);
    }
  } else {
    // If no arg, exit gracefully
    console.error(JSON.stringify({ error: 'No argument provided' }));
    process.exit(1);
  }
}

module.exports = { sendMail };

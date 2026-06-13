const { google } = require('googleapis');

function getOAuth2Client() {
  const client = new google.auth.OAuth2(
    process.env.GOOGLE_CLIENT_ID,
    process.env.GOOGLE_CLIENT_SECRET,
    'urn:ietf:wg:oauth:2.0:oob'
  );
  client.setCredentials({ refresh_token: process.env.GOOGLE_REFRESH_TOKEN });
  return client;
}

function getGmail() {
  return google.gmail({ version: 'v1', auth: getOAuth2Client() });
}

/**
 * Scan Gmail for PI lawyer threads dormant 60-90 days.
 * Returns up to `limit` prospects: { name, email, lastDate, subject, snippet }
 */
async function findDormantPIContacts(logger, limit = 5) {
  const gmail = getGmail();
  const prospects = [];

  try {
    const cutoffDays = 60;
    const staleBefore = Math.floor((Date.now() - cutoffDays * 86400_000) / 1000);
    const staleAfter  = Math.floor((Date.now() - 90   * 86400_000) / 1000);

    const piKeywords = ['personal injury', 'injury lawyer', 'law firm', 'PI lawyer',
                        'attorney', 'tort', 'accident', 'litigation'];
    const query = `(${piKeywords.map(k => `"${k}"`).join(' OR ')}) before:${staleBefore} after:${staleAfter} -in:sent`;

    const res = await gmail.users.messages.list({
      userId: 'me',
      q: query,
      maxResults: 20,
    });

    const messages = res.data.messages || [];
    logger.info(`Gmail dormant scan: found ${messages.length} candidate threads`);

    for (const msg of messages.slice(0, limit * 2)) {
      if (prospects.length >= limit) break;
      try {
        const full = await gmail.users.messages.get({ userId: 'me', id: msg.id, format: 'metadata',
          metadataHeaders: ['From', 'To', 'Subject', 'Date'] });

        const headers = full.data.payload.headers.reduce((acc, h) => {
          acc[h.name] = h.value; return acc;
        }, {});

        const from    = headers['From'] || '';
        const subject = headers['Subject'] || '(no subject)';
        const dateStr = headers['Date'] || '';
        const snippet = full.data.snippet || '';

        // Skip our own sent emails showing up as From
        const senderEmail = (from.match(/<(.+?)>/) || [, from])[1];
        if (senderEmail === process.env.SENDER_EMAIL ||
            senderEmail === 'emadvafa@gmail.com') continue;

        const name = from.replace(/<.*>/, '').trim().replace(/"/g, '') || senderEmail;

        prospects.push({ name, email: senderEmail, lastDate: dateStr, subject, snippet, source: 'gmail' });
      } catch (_) {}
    }
  } catch (err) {
    logger.warn(`Gmail scan failed: ${err.message}`);
  }

  return prospects;
}

/**
 * Create a Gmail draft. body is plain text.
 */
async function createDraft(to, subject, body) {
  const gmail = getGmail();
  const sender = process.env.SENDER_EMAIL;

  const raw = Buffer.from(
    `From: Emod Vafa <${sender}>\r\n` +
    `To: ${to}\r\n` +
    `Subject: ${subject}\r\n` +
    `Content-Type: text/plain; charset=utf-8\r\n` +
    `\r\n` +
    body
  ).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

  const res = await gmail.users.drafts.create({
    userId: 'me',
    requestBody: { message: { raw } },
  });

  return res.data.id;
}

module.exports = { findDormantPIContacts, createDraft };

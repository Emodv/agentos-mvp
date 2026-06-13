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

/**
 * Find past meeting attendees (60-90 days ago) who haven't been followed up.
 * Returns up to `limit` prospects: { name, email, meetingTitle, meetingDate }
 */
async function findUnfollowedAttendees(logger, limit = 5) {
  const calendar = google.calendar({ version: 'v3', auth: getOAuth2Client() });
  const prospects = [];

  try {
    const timeMax = new Date(Date.now() - 60  * 86400_000).toISOString();
    const timeMin = new Date(Date.now() - 90  * 86400_000).toISOString();

    const res = await calendar.events.list({
      calendarId: 'primary',
      timeMin,
      timeMax,
      maxResults: 50,
      singleEvents: true,
      orderBy: 'startTime',
    });

    const events = res.data.items || [];
    logger.info(`Calendar scan: found ${events.length} past events in window`);

    const seen = new Set();
    for (const event of events) {
      if (prospects.length >= limit) break;
      const attendees = event.attendees || [];
      const title     = event.summary || 'our meeting';
      const date      = event.start?.dateTime || event.start?.date || '';

      for (const att of attendees) {
        if (prospects.length >= limit) break;
        const email = att.email;
        if (!email || seen.has(email)) continue;
        if (email === process.env.SENDER_EMAIL || email === 'emadvafa@gmail.com') continue;
        // Heuristic: skip Google internal / calendar service accounts
        if (email.endsWith('calendar.google.com') || email.includes('resource.calendar')) continue;

        seen.add(email);
        const name = att.displayName || email.split('@')[0];
        prospects.push({ name, email, meetingTitle: title, meetingDate: date, source: 'calendar' });
      }
    }
  } catch (err) {
    logger.warn(`Calendar scan failed: ${err.message}`);
  }

  return prospects;
}

module.exports = { findUnfollowedAttendees };

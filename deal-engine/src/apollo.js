const fetch = require('node-fetch');

const APOLLO_BASE = 'https://api.apollo.io/v1';

const PI_TITLES = [
  'Personal Injury Lawyer', 'Personal Injury Attorney', 'PI Lawyer',
  'Trial Lawyer', 'Injury Lawyer', 'Accident Lawyer', 'Tort Lawyer',
];

const GTA_LOCATIONS = ['Toronto', 'Mississauga', 'Brampton', 'Hamilton', 'Ottawa', 'Ontario'];

/**
 * Search Apollo.io for PI lawyers in Ontario/GTA.
 * Returns up to `limit` prospects: { name, email, title, company, city }
 */
async function searchPILawyers(logger, limit = 5) {
  const apiKey = process.env.APOLLO_API_KEY;
  if (!apiKey) { logger.warn('APOLLO_API_KEY not set'); return []; }

  const prospects = [];

  try {
    const body = {
      api_key: apiKey,
      q_person_title: PI_TITLES.join(','),
      person_locations: GTA_LOCATIONS,
      organization_locations: GTA_LOCATIONS,
      person_industries: ['Law Practice'],
      contact_email_status: ['verified', 'guessed'],
      per_page: Math.min(limit * 3, 25),
      page: 1,
    };

    const res = await fetch(`${APOLLO_BASE}/mixed_people/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-cache' },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      logger.warn(`Apollo API returned ${res.status}: ${await res.text()}`);
      return [];
    }

    const data = await res.json();
    const people = data.people || [];
    logger.info(`Apollo search: found ${people.length} PI lawyers`);

    for (const p of people) {
      if (prospects.length >= limit) break;
      const email = p.email || (p.contact && p.contact.email);
      if (!email) continue;

      // Filter: prefer small to mid-size firms
      const headcount = p.organization?.estimated_num_employees || 0;
      if (headcount > 100) continue;

      prospects.push({
        name:    `${p.first_name || ''} ${p.last_name || ''}`.trim(),
        email,
        title:   p.title || 'Personal Injury Lawyer',
        company: p.organization?.name || '',
        city:    p.city || '',
        source:  'apollo',
      });
    }
  } catch (err) {
    logger.warn(`Apollo search failed: ${err.message}`);
  }

  return prospects;
}

module.exports = { searchPILawyers };

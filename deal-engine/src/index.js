require('dotenv').config({ path: require('path').join(__dirname, '..', '.env') });

const cron = require('node-cron');
const { Logger }                  = require('./logger');
const { findDormantPIContacts, createDraft } = require('./gmail');
const { findUnfollowedAttendees } = require('./calendar');
const { searchPILawyers }         = require('./apollo');
const { findGrowingPIFirms }      = require('./search');
const { writeEmail }              = require('./emailWriter');

const DRAFTS_PER_RUN  = parseInt(process.env.DRAFTS_PER_RUN  || '2', 10);
const CRON_SCHEDULE   = process.env.CRON_SCHEDULE || '0 */3 * * *'; // every 3 hours
const TEST_MODE       = process.argv.includes('--test');

async function run() {
  const logger  = new Logger();
  const sources = [];
  let   created = 0;
  const prospects = [];

  logger.info(`Starting Deal Engine run (target: ${DRAFTS_PER_RUN} drafts)`);

  // ── SOURCE 1: Gmail dormant contacts ─────────────────────────────────────
  try {
    const gmailLeads = await findDormantPIContacts(logger, DRAFTS_PER_RUN);
    if (gmailLeads.length) { prospects.push(...gmailLeads); sources.push('gmail'); }
  } catch (err) { logger.error(`Gmail source error: ${err.message}`); }

  // ── SOURCE 2: Google Calendar attendees ──────────────────────────────────
  if (prospects.length < DRAFTS_PER_RUN) {
    try {
      const calLeads = await findUnfollowedAttendees(logger, DRAFTS_PER_RUN - prospects.length);
      if (calLeads.length) { prospects.push(...calLeads); sources.push('calendar'); }
    } catch (err) { logger.error(`Calendar source error: ${err.message}`); }
  }

  // ── SOURCE 3: Apollo.io PI lawyers ───────────────────────────────────────
  if (prospects.length < DRAFTS_PER_RUN) {
    try {
      const apolloLeads = await searchPILawyers(logger, DRAFTS_PER_RUN - prospects.length);
      if (apolloLeads.length) { prospects.push(...apolloLeads); sources.push('apollo'); }
    } catch (err) { logger.error(`Apollo source error: ${err.message}`); }
  }

  // ── SOURCE 4: Claude web research ────────────────────────────────────────
  if (prospects.length < DRAFTS_PER_RUN) {
    try {
      const researchLeads = await findGrowingPIFirms(logger, DRAFTS_PER_RUN - prospects.length);
      if (researchLeads.length) { prospects.push(...researchLeads); sources.push('claude_research'); }
    } catch (err) { logger.error(`Claude research error: ${err.message}`); }
  }

  logger.info(`Total prospects gathered: ${prospects.length}`);

  // ── WRITE & DRAFT ─────────────────────────────────────────────────────────
  for (const prospect of prospects.slice(0, DRAFTS_PER_RUN)) {
    try {
      logger.info(`Writing email for ${prospect.name} <${prospect.email}> [${prospect.source}]`);
      const email = await writeEmail(prospect);
      logger.info(`  Path: ${email.path} | Subject: "${email.subject}"`);

      const draftId = await createDraft(email.to, email.subject, email.body);
      logger.info(`  ✓ Draft created: ${draftId}`);
      created++;
    } catch (err) {
      logger.error(`  Failed for ${prospect.email}: ${err.message}`);
    }
  }

  logger.summary(created, sources);

  if (created < DRAFTS_PER_RUN) {
    logger.warn(`Only ${created}/${DRAFTS_PER_RUN} drafts created this run.`);
  }

  return created;
}

// ── ENTRY POINT ───────────────────────────────────────────────────────────────

if (TEST_MODE) {
  console.log('Running in TEST MODE (single immediate run)…\n');
  run().then(n => {
    console.log(`\nDone. ${n} draft(s) created.`);
    process.exit(0);
  }).catch(err => {
    console.error('Fatal error:', err);
    process.exit(1);
  });
} else {
  console.log(`Deal Engine starting. Cron: "${CRON_SCHEDULE}"`);
  console.log('Running once immediately on startup…\n');

  run().catch(err => console.error('Startup run error:', err));

  cron.schedule(CRON_SCHEDULE, () => {
    console.log('\n--- Cron trigger ---');
    run().catch(err => console.error('Cron run error:', err));
  });
}

/**
 * HaqSetu — P1 Application Script
 *
 * Loads fixture data and renders the Civic Ledger interface.
 * Uses only textContent and createElement for DOM construction.
 * No eval(), no innerHTML with user data, no external libraries.
 * No backend calls. All data is static fixture JSON.
 */

"use strict";

/* ----------------------------------------------------------
   ICONS (inline SVG strings — safe, no external requests)
   ---------------------------------------------------------- */
const ICONS = {
  done:    '<svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M3 8.5L6.5 12 13 5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  ready:   '<svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="2"/></svg>',
  blocked: '<svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M8 3v5m0 3v.5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
  gated:   '<svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="4" y="7" width="8" height="6" rx="1" stroke="currentColor" stroke-width="1.8"/><path d="M5.5 7V5.5a2.5 2.5 0 015 0V7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  pass:    '<svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M3 8.5L6.5 12 13 5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  fail:    '<svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
  verify:  '<svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M8 3v5m0 3v.5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
  listing: '<svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="2"/><path d="M8 5v3l2 2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  info:    '<svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="2"/><path d="M8 7.5v4M8 5.5v.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
  chevron: '<svg aria-hidden="true" width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M3 4.5L6 7.5 9 4.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};

/* ----------------------------------------------------------
   BADGE CONFIG
   ---------------------------------------------------------- */
const BADGE_CONFIG = {
  ELIGIBLE:           { cls: 'badge--eligible',          icon: ICONS.pass,    label: 'Eligible'            },
  INELIGIBLE:         { cls: 'badge--ineligible',         icon: ICONS.fail,    label: 'Ineligible'          },
  NEEDS_VERIFICATION: { cls: 'badge--needs-verification', icon: ICONS.verify,  label: 'Needs Verification'  },
  LISTING_ONLY:       { cls: 'badge--listing-only',       icon: ICONS.listing, label: 'Listing Only'        },
  PASS:               { cls: 'badge--pass',               icon: ICONS.pass,    label: 'Meets Condition'     },
  FAIL:               { cls: 'badge--fail',               icon: ICONS.fail,    label: 'Does Not Meet'       },
  DONE:               { cls: 'badge--done',               icon: ICONS.done,    label: 'Done'                },
  READY:              { cls: 'badge--ready',              icon: ICONS.ready,   label: 'Ready'               },
  BLOCKED:            { cls: 'badge--blocked',            icon: ICONS.blocked, label: 'Blocked'             },
  GATED:              { cls: 'badge--gated',              icon: ICONS.gated,   label: 'Gated'               },
};

/* ----------------------------------------------------------
   SAFE DOM HELPERS
   ---------------------------------------------------------- */

/**
 * Create an element with optional class name.
 * @param {string} tag
 * @param {string} [cls]
 * @returns {HTMLElement}
 */
function el(tag, cls) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  return e;
}

/**
 * Create a text node.
 * @param {string} text
 * @returns {Text}
 */
function txt(text) {
  return document.createTextNode(String(text));
}

/**
 * Render an icon+label badge safely.
 * Uses innerHTML only for the trusted, hard-coded ICONS constant.
 * User/fixture text is always assigned via textContent.
 * @param {string} key
 * @returns {HTMLElement|null}
 */
function makeBadge(key) {
  const cfg = BADGE_CONFIG[key];
  if (!cfg) return null;
  const span = el('span', 'badge ' + cfg.cls);
  span.setAttribute('role', 'img');
  span.setAttribute('aria-label', cfg.label);
  // Icon is a trusted hard-coded constant — not user data.
  const iconWrap = el('span');
  iconWrap.innerHTML = cfg.icon; // safe: constant, no user input
  span.appendChild(iconWrap);
  const labelSpan = el('span');
  labelSpan.textContent = cfg.label;
  span.appendChild(labelSpan);
  return span;
}

/* ----------------------------------------------------------
   RENDER: EVIDENCE ROW
   ---------------------------------------------------------- */
function renderEvidence(evidence, parentEl) {
  if (!evidence) return;
  const toggleBtn = el('button', 'evidence-toggle');
  const iconWrap = el('span');
  iconWrap.innerHTML = ICONS.chevron; // trusted constant
  toggleBtn.appendChild(iconWrap);
  const toggleLabel = el('span');
  toggleLabel.textContent = 'View policy clause';
  toggleBtn.appendChild(toggleLabel);

  const detailDiv = el('div', 'condition-row__evidence evidence-detail');
  const excerpt = el('p', 'condition-row__evidence-excerpt');
  excerpt.textContent = evidence.excerpt || '';
  detailDiv.appendChild(excerpt);

  const source = el('p', 'condition-row__evidence-source');
  source.textContent = evidence.source_label || '';
  detailDiv.appendChild(source);

  if (evidence.fictional) {
    const fictionalNote = el('p', 'condition-row__evidence-fictional');
    fictionalNote.textContent = '⚠ Fictional — for demonstration only';
    detailDiv.appendChild(fictionalNote);
  }

  toggleBtn.addEventListener('click', function () {
    const isVisible = detailDiv.classList.contains('evidence-detail--visible');
    detailDiv.classList.toggle('evidence-detail--visible', !isVisible);
    toggleLabel.textContent = isVisible ? 'View policy clause' : 'Hide policy clause';
  });

  parentEl.appendChild(toggleBtn);
  parentEl.appendChild(detailDiv);
}

/* ----------------------------------------------------------
   RENDER: CONDITIONS LIST
   ---------------------------------------------------------- */
function renderConditions(conditions, container) {
  if (!conditions || conditions.length === 0) return;

  const heading = el('h3', 'section-label');
  heading.textContent = 'Eligibility Conditions';
  container.appendChild(heading);

  const list = el('div', 'conditions-list');

  conditions.forEach(function (cond) {
    const row = el('div', 'condition-row');

    const header = el('div', 'condition-row__header');
    const labelEl = el('div', 'condition-row__label');
    labelEl.textContent = cond.label || '';
    header.appendChild(labelEl);

    const badge = makeBadge(cond.result);
    if (badge) header.appendChild(badge);
    row.appendChild(header);

    if (cond.user_answer) {
      const answer = el('div', 'condition-row__answer');
      answer.textContent = 'Your answer: ' + cond.user_answer;
      row.appendChild(answer);
    }

    renderEvidence(cond.evidence, row);
    list.appendChild(row);
  });

  container.appendChild(list);
}

/* ----------------------------------------------------------
   RENDER: DECISION RAIL
   ---------------------------------------------------------- */
function renderDecisionRail(actionPlan, container) {
  if (!actionPlan || actionPlan.length === 0) return;

  const railCard = el('div', 'card');
  const heading = el('h2', 'decision-rail__heading');
  heading.textContent = 'Decision Rail — Next Steps';
  railCard.appendChild(heading);

  const rail = el('div', 'decision-rail');

  actionPlan.forEach(function (step) {
    const stepEl = el('div', 'rail-step');

    // Icon circle
    const iconEl = el('div', 'rail-step__icon rail-step__icon--' + step.status.toLowerCase());
    iconEl.setAttribute('aria-hidden', 'true');
    const iconMap = {
      done: ICONS.done, ready: ICONS.ready,
      blocked: ICONS.blocked, gated: ICONS.gated,
    };
    const iconSvg = iconMap[step.status.toLowerCase()];
    if (iconSvg) iconEl.innerHTML = iconSvg; // trusted constant

    stepEl.appendChild(iconEl);

    // Body
    const body = el('div', 'rail-step__body');
    const labelEl = el('div', 'rail-step__label');
    labelEl.textContent = step.label || '';
    body.appendChild(labelEl);

    // Status badge
    const badge = makeBadge(step.status);
    if (badge) body.appendChild(badge);

    // Reason / gate reason
    const reason = step.gate_reason || step.status_reason;
    if (reason) {
      const reasonEl = el('div', 'rail-step__reason');
      reasonEl.textContent = reason;
      body.appendChild(reasonEl);
    }

    if (step.document_type) {
      const docEl = el('div', 'rail-step__document');
      docEl.textContent = 'Document: ' + step.document_type;
      body.appendChild(docEl);
    }

    stepEl.appendChild(body);
    rail.appendChild(stepEl);
  });

  railCard.appendChild(rail);
  container.appendChild(railCard);
}

/* ----------------------------------------------------------
   RENDER: QUESTIONNAIRE SHELL
   ---------------------------------------------------------- */
function renderQuestionnaire(questionnaire, demoAnswers, container) {
  if (!questionnaire || questionnaire.length === 0) return;

  const card = el('div', 'card');
  const heading = el('h2');
  heading.textContent = 'Your Answers (Demo — Pre-filled)';
  card.appendChild(heading);

  const subNote = el('p', 'card__subtitle');
  subNote.textContent = 'In the live product this questionnaire will collect your answers. In P1 it shows pre-filled fictional responses to demonstrate the interface.';
  card.appendChild(subNote);

  const divider = el('div', 'divider');
  card.appendChild(divider);

  const form = el('form', 'questionnaire');
  form.setAttribute('aria-label', 'Eligibility questionnaire');
  form.addEventListener('submit', function (e) { e.preventDefault(); });

  questionnaire.forEach(function (q, index) {
    const block = el('fieldset', 'question-block');
    block.style.border = 'none';

    const legend = el('legend', 'question-block__label');
    legend.textContent = (index + 1) + '. ' + q.question;
    block.appendChild(legend);

    const options = el('div', 'question-block__options');
    options.setAttribute('role', 'radiogroup');

    q.options.forEach(function (opt) {
      const label = el('label', 'radio-option' + (opt.value === 'unknown' ? ' radio-option--dontknow' : ''));

      const input = document.createElement('input');
      input.type = 'radio';
      input.name = 'q_' + q.id;  // shared name = native mutual exclusion within this question
      input.value = opt.value;
      // Not disabled: native radio grouping handles mutual exclusion.
      // Demo defaults are initial values; the user can change them.
      if (opt.value === q.demo_answer) {
        input.checked = true;
        label.classList.add('radio-option--selected');
      }

      // Sync the visual .radio-option--selected class with the checked state.
      // The change event fires on the newly selected input; we clear all sibling
      // labels in this group first, then mark only the selected one.
      input.addEventListener('change', function () {
        // Clear selected style from every label in this question's option list
        options.querySelectorAll('.radio-option').forEach(function (siblingLabel) {
          siblingLabel.classList.remove('radio-option--selected');
        });
        // Apply selected style to the label that wraps the checked input
        label.classList.add('radio-option--selected');
      });

      const labelText = el('span');
      labelText.textContent = opt.label;

      label.appendChild(input);
      label.appendChild(labelText);
      options.appendChild(label);
    });

    block.appendChild(options);
    form.appendChild(block);
  });

  card.appendChild(form);
  container.appendChild(card);
}

/* ----------------------------------------------------------
   RENDER: ASSESSABLE SCENARIO
   ---------------------------------------------------------- */
function renderAssessableScenario(scenario, container) {
  // Fixture notice card
  const noticeCard = el('div', 'card');
  noticeCard.style.borderColor = '#FCD34D';
  noticeCard.style.background = '#FFFBEB';

  const noticeRow = el('div');
  noticeRow.style.display = 'flex';
  noticeRow.style.gap = '8px';
  noticeRow.style.alignItems = 'flex-start';

  const noticeIcon = el('span');
  noticeIcon.textContent = '⚠';
  noticeIcon.style.fontSize = '1.1rem';
  noticeIcon.style.flexShrink = '0';
  noticeRow.appendChild(noticeIcon);

  const noticeText = el('div');
  noticeText.style.fontSize = '0.85rem';
  noticeText.style.color = '#92400E';
  const noticeBold = el('strong');
  noticeBold.textContent = 'Fictional demonstration scenario. ';
  noticeText.appendChild(noticeBold);
  const noticeBody = txt(scenario.fixture_notice || '');
  noticeText.appendChild(noticeBody);
  noticeRow.appendChild(noticeText);
  noticeCard.appendChild(noticeRow);
  container.appendChild(noticeCard);

  // Outcome panel
  const outcomeCard = el('div', 'card');
  const outcomePanel = el('div', 'outcome-panel');

  const verdictRow = el('div', 'outcome-panel__verdict');
  const titleEl = el('div', 'outcome-panel__title');
  titleEl.textContent = scenario.name;
  verdictRow.appendChild(titleEl);

  if (scenario.assessment_outcome) {
    const badge = makeBadge(scenario.assessment_outcome);
    if (badge) verdictRow.appendChild(badge);
  }

  outcomePanel.appendChild(verdictRow);

  if (scenario.issuing_body) {
    const meta = el('p', 'card__subtitle');
    meta.textContent = scenario.issuing_body;
    outcomePanel.appendChild(meta);
  }

  if (scenario.assessment_summary) {
    const summary = el('p', 'outcome-panel__summary');
    summary.textContent = scenario.assessment_summary;
    outcomePanel.appendChild(summary);
  }

  outcomeCard.appendChild(outcomePanel);
  container.appendChild(outcomeCard);

  // Conditions from first pathway
  if (scenario.pathways && scenario.pathways.length > 0) {
    const condCard = el('div', 'card');
    const pathway = scenario.pathways[0];
    renderConditions(pathway.conditions, condCard);
    container.appendChild(condCard);
  }

  // Questionnaire shell
  if (scenario.questionnaire && scenario.questionnaire.length > 0) {
    renderQuestionnaire(scenario.questionnaire, {}, container);
  }
}

/* ----------------------------------------------------------
   RENDER: LISTING-ONLY SCENARIO
   ---------------------------------------------------------- */
function renderListingOnlyScenario(scenario, container) {
  const card = el('div', 'card');

  const header = el('div', 'card__header');
  const titleEl = el('div', 'card__title');
  titleEl.textContent = scenario.name;
  header.appendChild(titleEl);

  const fixtureLabel = el('span', 'card__fixture-label');
  fixtureLabel.textContent = 'Real Candidate';
  header.appendChild(fixtureLabel);
  card.appendChild(header);

  if (scenario.issuing_body) {
    const sub = el('p', 'card__subtitle');
    sub.textContent = scenario.issuing_body;
    card.appendChild(sub);
  }

  const badge = makeBadge('LISTING_ONLY');
  if (badge) card.appendChild(badge);

  const notice = el('div', 'listing-only-notice');
  const noticeIcon = el('span', 'listing-only-notice__icon');
  noticeIcon.textContent = 'ℹ';
  notice.appendChild(noticeIcon);

  const noticeText = el('div', 'listing-only-notice__text');
  const strong = el('strong');
  strong.textContent = 'No eligibility assessment available yet.';
  noticeText.appendChild(strong);
  noticeText.appendChild(txt(scenario.fixture_notice || 'Eligibility rules for this scheme have not yet been verified from official sources. A human verification checkpoint is required before this scheme can become assessable.'));
  notice.appendChild(noticeText);
  card.appendChild(notice);

  container.appendChild(card);
}

/* ----------------------------------------------------------
   RENDER: TABS
   ---------------------------------------------------------- */
function renderTabs(scenarios, tabsEl, panelsEl) {
  scenarios.forEach(function (scenario, index) {
    const btn = el('button', 'scheme-tab' + (index === 0 ? ' scheme-tab--active' : ''));
    btn.textContent = scenario.short_name || scenario.name;
    btn.setAttribute('role', 'tab');
    btn.setAttribute('aria-selected', index === 0 ? 'true' : 'false');
    btn.setAttribute('aria-controls', 'panel-' + scenario.id);
    btn.setAttribute('id', 'tab-' + scenario.id);

    btn.addEventListener('click', function () {
      // Deactivate all tabs
      tabsEl.querySelectorAll('.scheme-tab').forEach(function (t) {
        t.classList.remove('scheme-tab--active');
        t.setAttribute('aria-selected', 'false');
      });
      // Hide all panels
      panelsEl.querySelectorAll('.scheme-panel').forEach(function (p) {
        p.hidden = true;
      });
      // Activate clicked tab
      btn.classList.add('scheme-tab--active');
      btn.setAttribute('aria-selected', 'true');
      const panel = document.getElementById('panel-' + scenario.id);
      if (panel) panel.hidden = false;
    });

    tabsEl.appendChild(btn);
  });
}

/* ----------------------------------------------------------
   RENDER: FULL PAGE
   ---------------------------------------------------------- */
function renderApp(data) {
  const scenarios = data.scenarios;
  if (!scenarios || scenarios.length === 0) {
    renderEmptyState(document.getElementById('main-content'));
    return;
  }

  const mainContent = document.getElementById('main-content');
  mainContent.innerHTML = ''; // safe: reset before building

  // Tab bar
  const tabsEl = el('div', 'scheme-tabs');
  tabsEl.setAttribute('role', 'tablist');
  tabsEl.setAttribute('aria-label', 'Scheme scenarios');
  mainContent.appendChild(tabsEl);

  // Panel container
  const panelsEl = el('div');

  scenarios.forEach(function (scenario, index) {
    const panel = el('div', 'scheme-panel');
    panel.id = 'panel-' + scenario.id;
    panel.setAttribute('role', 'tabpanel');
    panel.setAttribute('aria-labelledby', 'tab-' + scenario.id);
    panel.hidden = index !== 0;

    if (scenario.readiness === 'ASSESSABLE') {
      const cols = el('div', 'layout-columns');

      // Left: conditions + questionnaire (60%)
      const leftCol = el('div', 'left-column');
      renderAssessableScenario(scenario, leftCol);

      // Right: Decision Rail (40%)
      const rightCol = el('div', 'right-column');
      renderDecisionRail(scenario.action_plan, rightCol);

      cols.appendChild(leftCol);
      cols.appendChild(rightCol);
      panel.appendChild(cols);
    } else {
      renderListingOnlyScenario(scenario, panel);
    }

    panelsEl.appendChild(panel);
  });

  mainContent.appendChild(panelsEl);
  renderTabs(scenarios, tabsEl, panelsEl);
}

/* ----------------------------------------------------------
   EMPTY AND ERROR STATES
   ---------------------------------------------------------- */
function renderEmptyState(container) {
  container.innerHTML = '';
  const state = el('div', 'card state-empty');
  const icon = el('span', 'state-empty__icon');
  icon.textContent = '📋';
  const title = el('div', 'state-empty__title');
  title.textContent = 'No scheme data loaded';
  const body = el('div', 'state-empty__body');
  body.textContent = 'Fixture data could not be found. Serve this project with: py -m http.server 8000';
  state.appendChild(icon);
  state.appendChild(title);
  state.appendChild(body);
  container.appendChild(state);
}

function renderErrorState(container, message) {
  container.innerHTML = '';
  const state = el('div', 'card state-error');
  const icon = el('span', 'state-error__icon');
  icon.textContent = '⚠';
  const title = el('div', 'state-error__title');
  title.textContent = 'Could not load fixture data';
  const body = el('div', 'state-error__body');
  body.textContent = message || 'An unexpected error occurred. Check the browser console.';
  state.appendChild(icon);
  state.appendChild(title);
  state.appendChild(body);
  container.appendChild(state);
}

/* ----------------------------------------------------------
   BOOTSTRAP
   ---------------------------------------------------------- */
(function init() {
  // Load fixture data via fetch (requires a local HTTP server)
  fetch('data/fixtures/demo.json')
    .then(function (response) {
      if (!response.ok) {
        throw new Error('HTTP ' + response.status + ' — ' + response.statusText);
      }
      return response.json();
    })
    .then(function (data) {
      renderApp(data);
    })
    .catch(function (err) {
      console.error('[HaqSetu] Failed to load fixture data:', err);
      const main = document.getElementById('main-content');
      if (main) {
        renderErrorState(main,
          'Could not load demo.json. ' +
          'Start a local server: py -m http.server 8000  ' +
          'then open http://localhost:8000 in your browser. ' +
          'Error: ' + err.message
        );
      }
    });
})();

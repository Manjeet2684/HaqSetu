/**
 * HaqSetu Stage P6/P9 Progressive API Integration Bridge (`js/haqsetu_api_client.js`)
 *
 * Connects the P1 Civic Ledger interface to the local FastAPI backend:
 * - Scheme Discovery Search & Readiness Filter (`GET /api/schemes`)
 * - Scheme Details, Pending Human Verification Checklist & Official Support (`GET /api/schemes/{id}`)
 * - Demo Eligibility Assessment (`POST /api/demo/assess`)
 * - Source-Grounded Policy Q&A with safe clickable source links (`POST /api/ask`)
 * - P9 AI/ML Assistant — intent + routing + Q&A (`POST /api/assistant`)
 * - P9 Scheme Recommender (`POST /api/recommend`)
 * - P9 ML Metrics Dashboard (`GET /api/ml/metrics`)
 *
 * Security rules:
 * - Uses `document.createElement` and `textContent` exclusively (zero raw innerHTML).
 * - Source links are validated as https:// only, opened with rel="noopener noreferrer".
 * - Never stores or logs applicant answers.
 */
(function () {
  "use strict";

  // Allowed official source domains for clickable policy links
  var ALLOWED_SOURCE_DOMAINS = [
    "scholarships.gov.in",
    "scholarship.up.gov.in",
    "pgportal.gov.in",
    "myscheme.gov.in",
    "education.gov.in",
    "socialjustice.gov.in",
    "minorityaffairs.gov.in",
    "india.gov.in"
  ];

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text !== undefined && text !== null) { node.textContent = String(text); }
    return node;
  }

  function clearChildren(node) {
    while (node.firstChild) { node.removeChild(node.firstChild); }
  }

  /** Safe HTTPS-only source link, restricted to known official domains. */
  function makeSafeSourceLink(url, label) {
    if (!url || typeof url !== "string") { return null; }
    var trimmed = url.trim();
    if (!trimmed.startsWith("https://")) { return null; }
    try {
      var parsed = new URL(trimmed);
      var host = parsed.hostname.toLowerCase();
      var isAllowed = ALLOWED_SOURCE_DOMAINS.some(function (d) {
        return host === d || host.endsWith("." + d);
      });
      if (!isAllowed) { return null; }
    } catch (e) { return null; }
    var a = el("a", null, label || trimmed);
    a.href = trimmed;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    return a;
  }

  function createWorkspaceContainer() {
    var existing = document.getElementById("hs-p6-live-workspace");
    if (existing) { return existing; }
    var container = el("section", "hs-p6-workspace");
    container.id = "hs-p6-live-workspace";
    container.setAttribute("aria-label", "HaqSetu live scholarship navigation workspace");

    // Place live API-backed features inside the main page flow, before the
    // legacy static preview. This keeps the footer at the end of the page.
    var mainContent = document.getElementById("main-content");
    if (mainContent && mainContent.parentNode) {
      mainContent.parentNode.insertBefore(container, mainContent);
    } else {
      var mainRoot = document.getElementById("main-root");
      (mainRoot || document.body).appendChild(container);
    }
    return container;
  }

  function wireEnterKey(input, button) {
    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
        button.click();
      }
    });
  }

  async function fetchJson(url, options) {
    var response = await fetch(url, options || {});
    var data;
    try {
      data = await response.json();
    } catch (_parseError) {
      if (!response.ok) {
        throw new Error("Request failed (HTTP " + response.status + "); the server returned a non-JSON error response.");
      }
      throw new Error("The server returned an unreadable response. Please retry.");
    }
    if (!response.ok) {
      var detail = (data && data.detail) ? data.detail : ("HTTP " + response.status);
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return data;
  }

  function buildWorkspaceIntro(root) {
    var intro = el("section", "hs-p6-intro");
    intro.appendChild(el("p", "hs-p6-eyebrow", "THE HAQSETU JOURNEY"));
    intro.appendChild(el("p", "hs-p6-intro-copy",
      "Discover opportunities, understand the evidence, and prepare your next step."
    ));

    var nav = el("nav", "hs-p6-quick-nav");
    nav.setAttribute("aria-label", "Navigate HaqSetu features");
    [
      ["hs-section-schemes", "Discover schemes"],
      ["hs-section-recommendations", "Get recommendations"],
      ["hs-section-assistant", "Ask the assistant"],
      ["hs-section-policy", "Explore evidence"],
      ["hs-section-demo", "Try fictional demo"],
      ["hs-section-metrics", "Technical evaluation"]
    ].forEach(function (item) {
      var link = el("a", "hs-p6-quick-link", item[1]);
      link.href = "#" + item[0];
      nav.appendChild(link);
    });
    intro.appendChild(nav);
    intro.appendChild(el("p", "hs-p6-intro-note",
      "Real scheme records remain listing-only until current official rules are human-verified. The demo uses invented rules."
    ));
    root.appendChild(intro);
  }

  // ---------------------------------------------------------------------------
  // Demo Assessment Panel
  // ---------------------------------------------------------------------------
  function buildDemoAssessPanel(root) {
    var section = el("div", "hs-p6-section");
    section.id = "hs-section-demo";
    var header = el("div", "hs-p6-header-row");
    header.appendChild(el("h2", "hs-p6-title", "Try a fictional assessment"));
    header.appendChild(el("span", "hs-p6-badge", "FICTIONAL DEMO ONLY"));
    section.appendChild(header);

    section.appendChild(el("div", "hs-p6-warning-banner",
      "FICTIONAL DEMO WARNING: This uses entirely invented rules and synthetic data. " +
      "Nothing here represents official government scholarship policy."
    ));

    var controls = el("div", "hs-p6-controls-grid");
    var answerNote = el("p", "hs-p6-section-copy",
      "Explore how a rules-based assessment responds to different answers. Every rule in this scenario is invented for demonstration only."
    );
    section.appendChild(answerNote);

    // Friendly controls preserve the exact answer tokens expected by the demo API.
    var questions = [
      { id: "q-marks", label: "Qualifying exam result", value: "above_80", options: [
        ["above_80", "Above 80%"], ["60_to_80", "60%–80%"], ["below_60", "Below 60%"], ["unknown", "I don't know"]
      ]},
      { id: "q-income", label: "Annual family income", value: "below_450000", options: [
        ["below_450000", "Up to ₹4,50,000"], ["above_450000", "More than ₹4,50,000"], ["unknown", "I don't know"]
      ]},
      { id: "q-enrollment", label: "Currently enrolled full-time", value: "yes", options: [
        ["yes", "Yes"], ["no", "No"], ["unknown", "I don't know"]
      ]},
      { id: "q-other-scholarship", label: "Receiving another central scholarship", value: "no", options: [
        ["yes", "Yes"], ["no", "No"], ["unknown", "I don't know"]
      ]}
    ];
    var answerInputs = {};
    questions.forEach(function (question) {
      var wrap = el("div", "hs-p6-field");
      var label = el("label", "hs-p6-field-label", question.label);
      var inp = el("select", "hs-p6-select");
      inp.id = "hs-demo-" + question.id;
      label.htmlFor = inp.id;
      inp.setAttribute("aria-label", question.label);
      question.options.forEach(function (option) {
        var choice = el("option", null, option[1]);
        choice.value = option[0];
        if (option[0] === question.value) { choice.selected = true; }
        inp.appendChild(choice);
      });
      answerInputs[question.id] = inp;
      wrap.appendChild(label);
      wrap.appendChild(inp);
      controls.appendChild(wrap);
    });
    section.appendChild(controls);

    var runBtn = el("button", "hs-p6-button", "Run Demo Assessment");
    section.appendChild(runBtn);

    var output = el("div", null);
    output.setAttribute("aria-live", "polite");
    output.setAttribute("aria-atomic", "false");
    section.appendChild(output);
    root.appendChild(section);

    runBtn.addEventListener("click", async function () {
      clearChildren(output);
      output.appendChild(el("p", null, "Running demo assessment..."));
      var answers = {};
      Object.keys(answerInputs).forEach(function (k) {
        answers[k] = answerInputs[k].value.trim();
      });
      try {
        var res = await fetchJson("/api/demo/assess", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ scenario_id: "demo-assessable", answers: answers, completed_action_ids: [] })
        });
        clearChildren(output);
        if (res.fictional_warning) {
          output.appendChild(el("div", "hs-p6-warning-banner", res.fictional_warning));
        }
        output.appendChild(el("div", "hs-p6-result-summary",
          "Demonstration outcome: " + (res.applicant_outcome || "No outcome (LISTING_ONLY)")));
        output.appendChild(el("p", null, res.summary));

        if (res.action_plan && res.action_plan.length > 0) {
          output.appendChild(el("h4", null, "Action Plan:"));
          var ul = el("ul", "hs-p6-list");
          res.action_plan.forEach(function (act) {
            var li = el("li", null, "[" + act.status + "] " + act.label);
            if (act.gate_reason) {
              li.appendChild(document.createTextNode(" — " + act.gate_reason));
            }
            ul.appendChild(li);
          });
          output.appendChild(ul);
        }
      } catch (err) {
        clearChildren(output);
        output.appendChild(el("p", null, "Demo assessment error: " + err.message));
      }
    });
  }

  // ---------------------------------------------------------------------------
  // Scheme Detail Panel renderer
  // ---------------------------------------------------------------------------
  function renderSchemeDetailPanel(targetBox, detailData) {
    clearChildren(targetBox);
    var scheme = detailData.scheme;

    var titleRow = el("div", "hs-p6-header-row");
    titleRow.appendChild(el("h3", "hs-p6-title", scheme.name + " (" + scheme.readiness + ")"));
    titleRow.appendChild(el("span", "hs-p6-badge",
      detailData.safe_for_automated_assessment
        ? "VERIFIED ASSESSABLE"
        : "LISTING ONLY — HUMAN VERIFICATION REQUIRED"
    ));
    targetBox.appendChild(titleRow);

    targetBox.appendChild(el("p", null, "Issuing Authority: " + scheme.issuing_body));
    if (scheme.verification_note) {
      targetBox.appendChild(el("div", "hs-p6-warning-banner", scheme.verification_note));
    }

    if (detailData.Pending_verification_requirements && detailData.Pending_verification_requirements.length > 0) {
      targetBox.appendChild(el("h4", null, "Mandatory Human Verification Checklist:"));
      var chkList = el("ul", "hs-p6-list");
      detailData.Pending_verification_requirements.forEach(function (item) {
        chkList.appendChild(el("li", null, item));
      });
      targetBox.appendChild(chkList);
    }

    if (scheme.support_channels && scheme.support_channels.length > 0) {
      targetBox.appendChild(el("h4", null, "Verified Official Channels:"));
      var supList = el("ul", "hs-p6-list");
      scheme.support_channels.forEach(function (ch) {
        var li = el("li", null, "[" + ch.channel_type + "] " + ch.label);
        if (ch.official_url) {
          var link = makeSafeSourceLink(ch.official_url, ch.official_url);
          if (link) {
            li.appendChild(document.createTextNode(" — "));
            li.appendChild(link);
          }
        }
        if (ch.contact_detail) {
          li.appendChild(el("span", null, " (" + ch.contact_detail + ")"));
        }
        supList.appendChild(li);
      });
      targetBox.appendChild(supList);
    }
  }

  // ---------------------------------------------------------------------------
  // Q&A Results renderer (with safe source links)
  // ---------------------------------------------------------------------------
  function renderAskResults(outputBox, askRes) {
    clearChildren(outputBox);
    if (askRes.fictional_warning) {
      outputBox.appendChild(el("div", "hs-p6-warning-banner", askRes.fictional_warning));
    }
    outputBox.appendChild(el("p", null, "Status: " + askRes.status + " — " + askRes.answer_message));

    if (askRes.passages && askRes.passages.length > 0) {
      askRes.passages.forEach(function (p) {
        var card = el("div", "hs-p6-passage-card");

        // Source line with safe clickable link
        var sourceLine = el("p", null, "Source: " + p.source_title);
        if (p.section_or_page) {
          sourceLine.appendChild(document.createTextNode(" (" + p.section_or_page + ")"));
        }
        if (p.academic_cycle) {
          sourceLine.appendChild(document.createTextNode(" | Cycle: " + p.academic_cycle));
        }
        sourceLine.appendChild(document.createTextNode(" | Score: " + p.similarity_score));
        card.appendChild(sourceLine);

        // Safe source URL link (https:// on allowed domains only)
        if (p.source_url) {
          var linkWrap = el("p", null, "Official Source: ");
          var safeLink = makeSafeSourceLink(p.source_url, p.source_url);
          if (safeLink) {
            linkWrap.appendChild(safeLink);
          } else {
            linkWrap.appendChild(document.createTextNode("[URL not shown — not on allowed domain list]"));
          }
          card.appendChild(linkWrap);
        }

        card.appendChild(el("p", null, "Excerpt: " + p.excerpt));
        outputBox.appendChild(card);
      });
    }
    outputBox.appendChild(el("p", null, askRes.eligibility_separation_notice));
    outputBox.appendChild(el("p", null, askRes.method_disclaimer));
  }

  // ---------------------------------------------------------------------------
  // Real Scheme Discovery Section
  // ---------------------------------------------------------------------------
  function buildDiscoverySection(root) {
    var discSection = el("div", "hs-p6-section");
    discSection.id = "hs-section-schemes";
    var discHeader = el("div", "hs-p6-header-row");
    discHeader.appendChild(el("h2", "hs-p6-title", "Explore real scheme records"));
    discHeader.appendChild(el("span", "hs-p6-badge", "Verification status shown"));
    discSection.appendChild(discHeader);

    var controls = el("div", "hs-p6-controls-grid");
    var searchInput = el("input", "hs-p6-input");
    searchInput.type = "search";
    searchInput.placeholder = "Search (e.g. PM-USP, Uttar Pradesh)...";
    searchInput.setAttribute("aria-label", "Search real scholarship schemes");

    var readinessSelect = el("select", "hs-p6-select");
    readinessSelect.setAttribute("aria-label", "Filter by readiness");
    [
      { value: "", label: "All Readiness States" },
      { value: "LISTING_ONLY", label: "Listing only — verification pending" },
      { value: "ASSESSABLE", label: "Assessable — rules verified" }
    ].forEach(function (opt) {
      var o = el("option", null, opt.label);
      o.value = opt.value;
      readinessSelect.appendChild(o);
    });

    var searchBtn = el("button", "hs-p6-button", "Search schemes");
    controls.appendChild(searchInput);
    controls.appendChild(readinessSelect);
    controls.appendChild(searchBtn);
    wireEnterKey(searchInput, searchBtn);
    discSection.appendChild(controls);

    var schemeListBox = el("div", null);
    schemeListBox.setAttribute("aria-live", "polite");
    schemeListBox.setAttribute("aria-atomic", "false");
    var schemeDetailBox = el("div", "hs-p6-passage-card");
    schemeDetailBox.setAttribute("aria-live", "polite");
    schemeDetailBox.setAttribute("aria-atomic", "false");
    discSection.appendChild(schemeListBox);
    discSection.appendChild(schemeDetailBox);
    root.appendChild(discSection);

    async function loadRealSchemes() {
      clearChildren(schemeListBox);
      schemeListBox.appendChild(el("p", null, "Loading..."));
      try {
        var params = new URLSearchParams();
        if (searchInput.value.trim()) { params.set("q", searchInput.value.trim()); }
        if (readinessSelect.value) { params.set("readiness", readinessSelect.value); }
        var url = "/api/schemes" + (params.toString() ? "?" + params.toString() : "");
        var schemes = await fetchJson(url);
        clearChildren(schemeListBox);
        if (!schemes || schemes.length === 0) {
          schemeListBox.appendChild(el("p", "hs-p6-empty-state", "No schemes matched those filters. Try a broader search."));
          return true;
        }
        var btnRow = el("div", "hs-p6-controls-grid");
        schemes.forEach(function (s) {
          var b = el("button", "hs-p6-button hs-p6-buttonSecondary",
            s.short_name + " [" + s.readiness + "]");
          b.addEventListener("click", async function () {
            try {
              var detail = await fetchJson("/api/schemes/" + encodeURIComponent(s.id));
              renderSchemeDetailPanel(schemeDetailBox, detail);
            } catch (err) {
              clearChildren(schemeDetailBox);
              schemeDetailBox.appendChild(el("p", null, "Error: " + err.message));
            }
          });
          btnRow.appendChild(b);
        });
        schemeListBox.appendChild(btnRow);
        var firstDetail = await fetchJson("/api/schemes/" + encodeURIComponent(schemes[0].id));
        renderSchemeDetailPanel(schemeDetailBox, firstDetail);
        return true;
      } catch (err) {
        clearChildren(schemeListBox);
        schemeListBox.appendChild(el("p", "hs-p6-error-state",
          "We couldn't connect to the scheme catalogue. " + err.message + " You can retry using Search schemes."));
        return false;
      }
    }

    searchBtn.addEventListener("click", loadRealSchemes);
    return loadRealSchemes;
  }

  // ---------------------------------------------------------------------------
  // Policy Q&A Section
  // ---------------------------------------------------------------------------
  function buildQASection(root) {
    var askSection = el("div", "hs-p6-section");
    askSection.id = "hs-section-policy";
    var askHeader = el("div", "hs-p6-header-row");
    askHeader.appendChild(el("h2", "hs-p6-title", "Ask about a policy clause"));
    askHeader.appendChild(el("span", "hs-p6-badge", "Evidence-grounded search"));
    askSection.appendChild(askHeader);

    var askControls = el("div", "hs-p6-controls-grid");
    var askInput = el("input", "hs-p6-input");
    askInput.type = "text";
    askInput.placeholder = "Ask about marks, income, enrollment...";
    askInput.setAttribute("aria-label", "Policy question");

    var scopeSelect = el("select", "hs-p6-select");
    scopeSelect.setAttribute("aria-label", "Evidence scope");
    [
      { value: "real:pmsp-central-sector", label: "Real: PM-USP Central Sector (Unverified)" },
      { value: "real:up-pre-matric-scholarship", label: "Real: UP Pre-Matric (Unverified)" },
      { value: "demo:demo-assessable", label: "Fictional Demo: Imaginary Merit Scholarship" }
    ].forEach(function (opt) {
      var o = el("option", null, opt.label);
      o.value = opt.value;
      scopeSelect.appendChild(o);
    });

    var askBtn = el("button", "hs-p6-button", "Search evidence");
    askControls.appendChild(askInput);
    askControls.appendChild(scopeSelect);
    askControls.appendChild(askBtn);
    wireEnterKey(askInput, askBtn);
    askSection.appendChild(askControls);

    var askOutput = el("div", null);
    askOutput.setAttribute("aria-live", "polite");
    askOutput.setAttribute("aria-atomic", "false");
    askSection.appendChild(askOutput);
    root.appendChild(askSection);

    askBtn.addEventListener("click", async function () {
      var qText = askInput.value.trim();
      if (qText.length < 2) {
        clearChildren(askOutput);
        askOutput.appendChild(el("p", null, "Please enter at least 2 characters."));
        return;
      }
      var parts = scopeSelect.value.split(":");
      var isDemo = parts[0] === "demo";
      var targetId = parts[1];
      clearChildren(askOutput);
      askOutput.appendChild(el("p", null, "Searching policy evidence..."));
      try {
        var res = await fetchJson("/api/ask", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: qText, scheme_id: targetId, include_fictional_demo: isDemo, top_k: 3 })
        });
        renderAskResults(askOutput, res);
      } catch (err) {
        clearChildren(askOutput);
        askOutput.appendChild(el("p", null, "Retrieval error: " + err.message));
      }
    });
  }

  // ---------------------------------------------------------------------------
  // P9 — AI Assistant Section (POST /api/assistant)
  // ---------------------------------------------------------------------------
  function buildAssistantSection(root) {
    var section = el("div", "hs-p6-section");
    section.id = "hs-section-assistant";
    var header = el("div", "hs-p6-header-row");
    header.appendChild(el("h2", "hs-p6-title", "Ask the HaqSetu assistant"));
    header.appendChild(el("span", "hs-p6-badge", "Intent-guided navigation"));
    section.appendChild(header);

    section.appendChild(el("p", null,
      "Type any scholarship question. The assistant classifies your intent and routes to the " +
      "appropriate action. Confidence scores are relative rankings, not calibrated probabilities."
    ));

    var controls = el("div", "hs-p6-controls-grid");
    var queryInput = el("input", "hs-p6-input");
    queryInput.type = "text";
    queryInput.placeholder = "e.g. Am I eligible? / Find me a scholarship / How to file grievance?";
    queryInput.setAttribute("aria-label", "Assistant query");
    var askBtn = el("button", "hs-p6-button", "Find the right next step");
    controls.appendChild(queryInput);
    controls.appendChild(askBtn);
    wireEnterKey(queryInput, askBtn);
    section.appendChild(controls);

    var output = el("div", null);
    output.setAttribute("aria-live", "polite");
    output.setAttribute("aria-atomic", "false");
    section.appendChild(output);
    root.appendChild(section);

    askBtn.addEventListener("click", async function () {
      var q = queryInput.value.trim();
      if (q.length < 2) {
        clearChildren(output);
        output.appendChild(el("p", null, "Please enter at least 2 characters."));
        return;
      }
      clearChildren(output);
      output.appendChild(el("p", null, "Classifying intent..."));
      try {
        var res = await fetchJson("/api/assistant", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: q, top_k: 3 })
        });
        clearChildren(output);

        // Intent result
        var intentBox = el("div", "hs-p6-passage-card");
        intentBox.appendChild(el("strong", null, "Detected Intent: "));
        intentBox.appendChild(document.createTextNode(res.intent.predicted_intent));
        intentBox.appendChild(el("br"));
        intentBox.appendChild(el("em", null, res.intent.confidence_notice));
        output.appendChild(intentBox);

        // Top confidence scores
        var scores = res.intent.confidence_scores;
        if (scores && Object.keys(scores).length > 0) {
          var scoreList = el("ul", "hs-p6-list");
          Object.entries(scores)
            .sort(function (a, b) { return b[1] - a[1]; })
            .slice(0, 4)
            .forEach(function (pair) {
              scoreList.appendChild(el("li", null,
                pair[0] + ": " + Number(pair[1]).toFixed(3)
              ));
            });
          output.appendChild(el("p", "hs-p6-score-note", "Relative class scores (ranking hints, not calibrated probabilities):"));
          output.appendChild(scoreList);
        }

        // Routing advice
        output.appendChild(el("p", null, "Routing Advice: " + res.routing_advice));

        // Recommendations (for FIND_SCHEME intent)
        if (res.recommendations && res.recommendations.length > 0) {
          output.appendChild(el("h4", null, "Recommended Schemes:"));
          output.appendChild(el("p", null, res.recommendation_disclaimer));
          var recList = el("ul", "hs-p6-list");
          res.recommendations.forEach(function (r) {
            recList.appendChild(el("li", null,
              r.scheme_name + " [" + r.readiness + "] — Score: " + r.similarity_score +
              " | " + r.match_reason
            ));
          });
          output.appendChild(recList);
        }

        // Q&A result (for non-FIND_SCHEME in-scope intents)
        if (res.ask_response) {
          output.appendChild(el("h4", null, "Policy Q&A Result:"));
          renderAskResults(output, res.ask_response);
        }
      } catch (err) {
        clearChildren(output);
        output.appendChild(el("p", null, "Assistant error: " + err.message));
      }
    });
  }

  // ---------------------------------------------------------------------------
  // P9 — Recommender Section (POST /api/recommend)
  // ---------------------------------------------------------------------------
  function buildRecommenderSection(root) {
    var section = el("div", "hs-p6-section");
    section.id = "hs-section-recommendations";
    var header = el("div", "hs-p6-header-row");
    header.appendChild(el("h2", "hs-p6-title", "Get scheme recommendations"));
    header.appendChild(el("span", "hs-p6-badge", "Content similarity"));
    section.appendChild(header);

    section.appendChild(el("p", null,
      "Recommendations are based on keyword similarity to scheme catalogue metadata only — " +
      "NOT an eligibility assessment."
    ));

    var controls = el("div", "hs-p6-controls-grid");
    var queryInput = el("input", "hs-p6-input");
    queryInput.type = "text";
    queryInput.placeholder = "e.g. college scholarship central government";
    queryInput.setAttribute("aria-label", "Recommendation query");
    var recBtn = el("button", "hs-p6-button", "Find matching schemes");
    controls.appendChild(queryInput);
    controls.appendChild(recBtn);
    wireEnterKey(queryInput, recBtn);
    section.appendChild(controls);

    var output = el("div", null);
    output.setAttribute("aria-live", "polite");
    output.setAttribute("aria-atomic", "false");
    section.appendChild(output);
    root.appendChild(section);

    recBtn.addEventListener("click", async function () {
      var q = queryInput.value.trim();
      if (q.length < 2) {
        clearChildren(output);
        output.appendChild(el("p", null, "Please enter at least 2 characters."));
        return;
      }
      clearChildren(output);
      output.appendChild(el("p", null, "Fetching recommendations..."));
      try {
        var res = await fetchJson("/api/recommend", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: q, top_k: 3, include_fictional: false })
        });
        clearChildren(output);
        output.appendChild(el("p", null, res.disclaimer));
        if (!res.recommendations || res.recommendations.length === 0) {
          output.appendChild(el("p", null, "No schemes matched your query."));
          return;
        }
        var recList = el("ul", "hs-p6-list");
        res.recommendations.forEach(function (r) {
          var li = el("li", null,
            r.scheme_name + " [" + r.readiness + "] — Score: " + r.similarity_score +
            " | " + r.match_reason
          );
          recList.appendChild(li);
        });
        output.appendChild(recList);
      } catch (err) {
        clearChildren(output);
        output.appendChild(el("p", null, "Recommender error: " + err.message));
      }
    });
  }

  // ---------------------------------------------------------------------------
  // P9 — ML Metrics Dashboard (GET /api/ml/metrics)
  // ---------------------------------------------------------------------------
  function buildMetricsDashboard(root) {
    var section = el("div", "hs-p6-section");
    section.id = "hs-section-metrics";
    var header = el("div", "hs-p6-header-row");
    header.appendChild(el("h2", "hs-p6-title", "Model and retrieval evaluation"));
    header.appendChild(el("span", "hs-p6-badge", "Synthetic smoke benchmarks"));
    section.appendChild(header);

    section.appendChild(el("div", "hs-p6-warning-banner",
      "All metrics are synthetic in-distribution smoke benchmarks. " +
      "They verify implementation correctness, not real-world generalisation accuracy."
    ));

    var loadBtn = el("button", "hs-p6-button", "View evaluation results");
    section.appendChild(loadBtn);

    var output = el("div", null);
    output.setAttribute("aria-live", "polite");
    output.setAttribute("aria-atomic", "false");
    section.appendChild(output);
    root.appendChild(section);

    loadBtn.addEventListener("click", async function () {
      clearChildren(output);
      output.appendChild(el("p", null, "Running benchmarks..."));
      try {
        var metrics = await fetchJson("/api/ml/metrics");
        clearChildren(output);

        // Retrieval benchmark
        if (metrics.retrieval_benchmark) {
          var rb = metrics.retrieval_benchmark;
          output.appendChild(el("h4", null, "Policy Retrieval (10 synthetic queries):"));
          var rbList = el("ul", "hs-p6-list");
          rbList.appendChild(el("li", null, "Top-1 Accuracy: " + rb.top1_accuracy));
          rbList.appendChild(el("li", null, "Top-3 Recall: " + rb.top3_recall));
          rbList.appendChild(el("li", null, "MRR: " + rb.mean_reciprocal_rank));
          rbList.appendChild(el("li", null, "Refusal Accuracy: " + rb.refusal_accuracy));
          output.appendChild(rbList);
        }

        // Intent classifier
        if (metrics.intent_classifier) {
          var ic = metrics.intent_classifier;
          output.appendChild(el("h4", null, "Intent Classifier (in-sample):"));
          var icList = el("ul", "hs-p6-list");
          icList.appendChild(el("li", null, "Accuracy: " + ic.accuracy));
          icList.appendChild(el("li", null, "Macro F1: " + ic.macro_f1));
          icList.appendChild(el("li", null, ic.note || ""));
          output.appendChild(icList);
        }

        // Recommender
        if (metrics.recommender_benchmark) {
          var rec = metrics.recommender_benchmark;
          output.appendChild(el("h4", null, "Scheme Recommender (12 synthetic queries):"));
          var recList = el("ul", "hs-p6-list");
          recList.appendChild(el("li", null, "Top-1 Accuracy: " + rec.top1_accuracy));
          recList.appendChild(el("li", null, "MRR: " + rec.mean_reciprocal_rank));
          output.appendChild(recList);
        }

        output.appendChild(el("p", null, metrics.notice || ""));
      } catch (err) {
        clearChildren(output);
        output.appendChild(el("p", null, "Metrics error: " + err.message));
      }
    });
  }

  // ---------------------------------------------------------------------------
  // Bootstrap all panels
  // ---------------------------------------------------------------------------
  async function initHaqSetuBridge() {
    var root = createWorkspaceContainer();
    clearChildren(root);
    buildWorkspaceIntro(root);

    // Follow a user-centred journey: discover, explore options, ask, and inspect the demo.
    var loadRealSchemes = buildDiscoverySection(root);
    buildRecommenderSection(root);
    buildAssistantSection(root);
    buildQASection(root);
    buildDemoAssessPanel(root);
    buildMetricsDashboard(root);

    // Only hide the static prototype when the live scheme API has actually responded.
    var catalogueAvailable = await loadRealSchemes();
    if (catalogueAvailable) {
      document.body.classList.add("hs-live-mode");
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initHaqSetuBridge);
  } else {
    initHaqSetuBridge();
  }
})();

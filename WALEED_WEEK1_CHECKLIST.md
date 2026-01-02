# Waleed's Week 1 Checklist - Agent & Design Work

**Goal**: Optimize agents and design user pipeline while friend aggregates books

---

## Monday: Agent Prompt Review

### Morning (2-3 hours)
- [ ] Read all 3 agent files:
  - [ ] `app/agents/ask_agent.py` - Read the system prompt
  - [ ] `app/agents/reading_router.py` - Read the system prompt  
  - [ ] `app/agents/text_companion.py` - Read the system prompt
- [ ] Document current prompts in a Google Doc or notes file
- [ ] List what's good and what's missing in each

### Afternoon (2-3 hours)
- [ ] Rewrite Ask Agent prompt with:
  - [ ] Clear constraints ("only use books in the list")
  - [ ] 3 few-shot examples (question → domain classification)
  - [ ] Failure case handling ("say 'I don't know' if unclear")
- [ ] Test locally with 10 questions
- [ ] Commit changes

### Evening (Optional)
- [ ] Read about prompt engineering best practices
- [ ] Document your prompting strategy

---

## Tuesday: Router & Companion Prompts

### Morning (2-3 hours)
- [ ] Rewrite Reading Router prompt with:
  - [ ] Better path selection logic
  - [ ] Clearer output format
  - [ ] Few-shot examples
- [ ] Test with 10 routing scenarios
- [ ] Commit changes

### Afternoon (2-3 hours)
- [ ] Rewrite Text Companion prompt with:
  - [ ] Strict "only explain selected text" constraint
  - [ ] Examples of good vs bad responses
  - [ ] Tone guidance (helpful teacher, not know-it-all)
- [ ] Test with 5 text selections
- [ ] Commit changes

---

## Wednesday: Agent Testing & Edge Cases

### Morning (2 hours)
- [ ] Create test set of 50 diverse questions:
  - 10 philosophy questions
  - 10 strategy questions
  - 10 psychology questions
  - 10 technology questions
  - 5 off-topic questions (should fail gracefully)
  - 5 adversarial questions (prompt injection attempts)
- [ ] Save in `test_questions.md`

### Afternoon (3 hours)
- [ ] Run all 50 questions through the system
- [ ] Document results:
  - How many routed correctly?
  - How many failed gracefully?
  - How many broke?
- [ ] Fix any broken cases
- [ ] Update prompts based on findings

---

## Thursday: User Pipeline Design

### Morning (2 hours)
- [ ] Sketch user request flow on paper/whiteboard:
  - What happens at each stage?
  - What does user see?
  - What's happening in the backend?
- [ ] Take photo or digitize sketch

### Afternoon (3 hours)
- [ ] Create mockup: `mockups/10-request-status.html`
- [ ] Show all stages:
  ```
  ⏳ Request submitted (12:00 PM)
  🔍 Searching across 15 sources... (12:01 PM)
  📊 Found 23 potential sources (12:02 PM)
  ⚖️  Scoring sources for quality... (12:02 PM)
  👁️ Under human review (12:05 PM)
  ✅ Approved by curator (12:15 PM)
  📥 Acquiring book... (12:16 PM)
  📚 Added to library! (12:20 PM)
  ```
- [ ] Make it look good with CSS
- [ ] Show to someone for feedback

---

## Friday: Testing & Documentation

### Morning (2 hours)
- [ ] Full manual test of the app:
  - [ ] Register new account
  - [ ] Browse library
  - [ ] Read a book
  - [ ] Create highlight
  - [ ] Add annotation
  - [ ] Ask a question
  - [ ] Get routing results
  - [ ] Read recommended chapter
  - [ ] Request a book
  - [ ] Admin: view requests
- [ ] Document any bugs in `KNOWN_ISSUES.md`

### Afternoon (2 hours)
- [ ] Write `AGENT_OPTIMIZATION_REPORT.md`:
  - What you changed
  - Test results (50 questions)
  - Accuracy improvements
  - Remaining issues
- [ ] Commit all week's work
- [ ] Sync with friend: show mockup, discuss progress

---

## Quick Wins (Do Anytime)

- [ ] **Review domain assignments** of existing 193 books
  - Pick 20 random books
  - Check if domains make sense
  - Create reclassification list if needed

- [ ] **Improve mock responses**
  - Currently in `app/agents/*.py` - look for mock mode logic
  - Make them more realistic and varied
  
- [ ] **Test on mobile**
  - Open app on your phone
  - Try reading, highlighting
  - Document mobile issues

- [ ] **Write empty state copy**
  - My Library when empty: "Save books to see them here"
  - Wishlist when empty: "Request books you want to read"
  - Routing with no results: "I couldn't find relevant reading. Try browsing the library."

---

## Daily Sync Questions (5 min with friend)

1. **Him**: "How many books ingested today?" "Any blockers?"
2. **You**: "Here's what I finished" "Here's what I'm working on"
3. **Both**: "Are we on track for 2-week timeline?"

---

## Success Metrics for Week 1

By Friday EOD:
- [ ] All 3 agent prompts are improved
- [ ] 50-question test set exists with results documented
- [ ] User pipeline mockup is complete and looks good
- [ ] Agent optimization report is written
- [ ] You've done a full manual test and documented issues

**Then**: Start Week 2 work (infrastructure planning + content quality)

---

## Time Budget

**Total per day**: 4-6 hours of focused work
**Total per week**: 20-30 hours

This is in parallel with friend's book aggregation work. You're not blocked by each other.

---

## The Goal

By the time he finishes aggregating 1300 books, you'll have:
- **Optimized agents** that route accurately and handle edge cases
- **Designed user pipeline** that shows value and provides legal cover
- **Tested everything** so you know what works and what doesn't
- **Planned infrastructure** so Phase 2 execution is fast

**This is how you de-risk the launch. Start today with agent prompts.**

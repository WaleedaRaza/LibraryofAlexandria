# Parallel Work Strategy - All Eggs in Different Baskets

**The Situation**: Friend is aggregating 1300 books. What should Waleed do?

**The Answer**: Work on everything that's NOT blocked by book count.

---

## The Parallel Tracks

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRIEND'S TRACK                          │
│                                                                 │
│  Week 1-2: Book Aggregation (Phase 1)                          │
│  ├─ Discovery pipeline                                         │
│  ├─ Scoring system                                             │
│  ├─ Ingestion automation                                       │
│  └─ Target: 1300 books indexed                                 │
│                                                                 │
│  Progress: ████████████░░░░░░░░ 60% → 100%                     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                        WALEED'S TRACK                           │
│                                                                 │
│  Week 1: Agent Optimization & User Pipeline Design             │
│  ├─ Optimize all 3 agent prompts                               │
│  ├─ Test with 50 diverse questions                             │
│  ├─ Design user request status feed                            │
│  └─ Create status mockup                                       │
│                                                                 │
│  Week 2: Infrastructure Planning & Content Quality             │
│  ├─ Research Postgres providers                                │
│  ├─ Plan security implementation                               │
│  ├─ Choose deployment platform                                 │
│  ├─ Refine taxonomy for scale                                  │
│  ├─ Audit domain classifications                               │
│  └─ Polish UX (empty states, errors)                           │
│                                                                 │
│  Progress: ░░░░░░░░░░░░░░░░░░░░ 0% → 100%                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Why This Works

### No Blocking Dependencies
- Agent optimization doesn't need 1300 books (works with 193)
- User pipeline design is independent of book count
- Infrastructure planning doesn't require books at all
- UX polish can happen anytime

### High-Value Work
Every item on Waleed's track is:
- ✅ On the critical path to launch
- ✅ High leverage (makes everything else better)
- ✅ Requires design/architecture thinking (Waleed's strength)
- ✅ Can be done in parallel with aggregation

### Risk Mitigation
By Week 2 end, you'll have:
- **Proven agents** (tested with 50 questions, optimized)
- **Designed differentiator** (user status feed mockup)
- **Infrastructure plan** (ready to execute Phase 2 fast)
- **Quality baseline** (taxonomy refined, domains audited)
- **Polish plan** (UX improvements documented)

If book aggregation hits issues, you haven't lost time. If it finishes early, you're ready to execute Phase 2-3 immediately.

---

## The Timeline

```
CURRENT STATE (Week 0):
┌────────────────┐
│ 193 books      │
│ Basic agents   │
│ Local only     │
└────────────────┘

AFTER 2 WEEKS:
┌────────────────────────────────────┐
│ 1300 books indexed (Friend)        │
│ Optimized agents (Waleed)          │
│ User pipeline designed (Waleed)    │
│ Infrastructure planned (Waleed)    │
│ Ready for Phase 2 execution        │
└────────────────────────────────────┘

WEEK 3-4: Phase 2 & 3 Execution
Both work together:
- Friend: Database migration, security, deployment
- Waleed: Rate limiting, cost tracking, monitoring

WEEK 5-6: Phase 4 Hardening
Both work together:
- Testing, security audit, polish, launch prep

WEEK 7: 🚀 LAUNCH
```

---

## Waleed's 2-Week Roadmap

### Week 1 Focus: **Agents & Design**

| Day | Morning | Afternoon |
|-----|---------|-----------|
| Mon | Review agent prompts | Rewrite Ask Agent prompt |
| Tue | Rewrite Router prompt | Rewrite Companion prompt |
| Wed | Create 50-question test | Run tests, document results |
| Thu | Sketch user pipeline | Build status feed mockup |
| Fri | Full manual testing | Write optimization report |

**Deliverables**:
- ✅ Improved prompts for all 3 agents
- ✅ 50-question test results
- ✅ User pipeline mockup (`mockups/10-request-status.html`)
- ✅ Agent optimization report

### Week 2 Focus: **Infrastructure & Quality**

| Day | Morning | Afternoon |
|-----|---------|-----------|
| Mon | Research Postgres options | Document database plan |
| Tue | Research bcrypt & sessions | Document security plan |
| Wed | Compare Render vs Fly.io | Document deployment plan |
| Thu | Review taxonomy | Audit book domains |
| Fri | Write empty state copy | Polish error messages |

**Deliverables**:
- ✅ Infrastructure plan document
- ✅ Refined taxonomy
- ✅ Domain reclassification list
- ✅ UX improvements
- ✅ Smoke tests document

---

## Daily Coordination

### 5-Minute Daily Sync
**Friend**: "Ingested X books today, no blockers"
**Waleed**: "Finished agent prompts, testing tomorrow"
**Both**: Check if timeline is still realistic

### Weekly Sync (30 min Friday)
- Demo what you built (friend shows books, Waleed shows mockup)
- Discuss any architectural decisions needed
- Adjust next week's priorities
- Celebrate progress

---

## The Advantage

When book aggregation is done, you won't say:
> "OK, now what do we do?"

You'll say:
> "Books are done. Agents are optimized. User pipeline is designed. Infrastructure is planned. Let's execute Phase 2-3 and ship this."

**That's the difference between a 8-week launch and a 6-week launch.**

---

## Start Today

**Waleed's first task** (today, 2-3 hours):
1. Open `app/agents/ask_agent.py`
2. Read the system prompt
3. Rewrite it with clear constraints and examples
4. Test with 10 questions
5. Document what improved

**That's it. No need to wait for books. Start optimizing.**

---

## Files You Need

- **Your roadmap**: `WALEED_PARALLEL_WORK.md` (detailed plan)
- **This week**: `WALEED_WEEK1_CHECKLIST.md` (daily checklist)
- **Friend's roadmap**: `ONBOARDING.md` (he reads Phase 1 section)

---

## The Mindset

You're not "waiting for books to be ready."

You're **building the foundation** that makes those books valuable:
- The routing that helps users find them
- The pipeline that shows the work
- The infrastructure that scales
- The quality that builds trust

**Books are content. You're building the platform.**

---

**All eggs in different baskets. Both critical. No wasted time.**

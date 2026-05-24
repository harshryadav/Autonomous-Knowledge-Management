# Autonomous Knowledge Management — Sprint-Based Project Plan

## 🧠 Core Strategy

**Instead of siloed roles:**
- Person A = extraction
- Person B = graph  
- Person C = Q&A

**We do:**
- Each week = a working mini-system (even if simple)
- By Week 2, we already have: ingestion → extraction → retrieval → answer (even if crude)

---

## 👥 Team Structure (Harsh + Utkrisht)

### 🔵 Harsh (You) → Retrieval + Intelligence Layer
- Embeddings
- Semantic search
- Q&A system
- Gap detection + doc generation

### 🟢 Utkrisht → Data + Structure Layer
- Ingestion
- Parsing
- Entity extraction
- Knowledge graph

### 🤝 Shared (VERY IMPORTANT)
- Entity schema
- Linking logic
- Integration

---

## 📅 Sprint Breakdown

### 🚀 Sprint 1 — "Make It Work (End-to-End, Ugly Version)"

**Duration:** Week 1  
**Goal:** You can already ask "What does this repo do?" and get a basic answer.

#### 🔵 Harsh Tasks
- [ ] Set up embeddings using Sentence-BERT
- [ ] Build simple vector search (FAISS)
- [ ] Input: README + comments
- [ ] Output: retrieve relevant chunks

#### 🟢 Utkrisht Tasks
- [ ] GitHub ingestion (clone repos)
- [ ] Extract:
  - [ ] Files
  - [ ] Functions (AST)
  - [ ] Comments

#### 🤝 Integration (CRITICAL)
- [ ] Store extracted text in shared format:
```json
{
  "type": "comment",
  "content": "...",
  "file": "x.py",
  "function": "foo"
}
```

**✅ Sprint 1 Demo Criteria**
- Input: query
- Output: retrieved text chunks
- *Note: No graph, no ADRs yet — that's fine.*

---

### ⚙️ Sprint 2 — "Add Meaning (Extraction + Linking)"

**Duration:** Week 2  
**Goal:** System starts understanding concepts and relationships

#### 🟢 Utkrisht Tasks
- [ ] Implement entity extraction:
  - [ ] Components
  - [ ] Functions
  - [ ] Decisions (from commits)
- [ ] Basic NER using spaCy

#### 🔵 Harsh Tasks
- [ ] Improve retrieval:
  - [ ] Chunking strategy
  - [ ] Better embeddings
- [ ] Start simple Q&A wrapper:
  - [ ] Retrieved context → LLM → answer

#### 🤝 Joint Task (MOST IMPORTANT THIS WEEK)
- [ ] Implement entity linking:
  - [ ] **Phase 1 (Start simple):** "cache" ↔ "CacheManager"
  - [ ] **Phase 2 (Improve):** 
    - [ ] Embedding similarity
    - [ ] Same file proximity

**✅ Sprint 2 Demo Criteria**
- Query: "Where is caching used?"
- System returns:
  - Code
  - Comments
  - Maybe commit
- *This positions you ahead — most teams won't even have ingestion done.*

---

### 🧩 Sprint 3 — "Knowledge Graph + Why Reasoning"

**Duration:** Week 3  
**Goal:** Answer "Why was this implemented?"

#### 🟢 Utkrisht Tasks
- [ ] Build graph using Neo4j or networkx
- [ ] Add nodes:
  - [ ] Components
  - [ ] Decisions
- [ ] Add edges:
  - [ ] `affects`
  - [ ] `introduced_by`

#### 🔵 Harsh Tasks
- [ ] Implement hybrid retrieval:
  - [ ] Vector search
  - [ ] Expand via graph
- [ ] Build "why-Q&A":
  - [ ] Combine: ADR + commit + comment

#### 🤝 Integration
- [ ] Pipeline: Query → Vector Search → Graph Expansion → Context → Answer

**✅ Sprint 3 Demo Criteria**
- Query: "Why is caching used?"
- Output:
  - Commit message
  - Comment
  - Explanation
- *This is your core wow moment*

---

### 🔍 Sprint 4 — "Gap Detection + Polish"

**Duration:** Week 4  
**Goal:** System becomes useful, not just cool

#### 🔵 Harsh Tasks
- [ ] Implement gap detection:
  - [ ] `gap_score = complexity * (1 - doc_coverage)`
  - [ ] Generate doc stubs (LLM)

#### 🟢 Utkrisht Tasks
- [ ] Add ADR ingestion
- [ ] Improve graph quality
- [ ] Clean entity linking

#### 🤝 Shared Tasks
- [ ] Evaluation metrics
- [ ] Demo UI (simple CLI or web)

**✅ Final Demo Criteria**
Show end-to-end flow:
1. Repo ingestion
2. Knowledge graph construction
3. Query: "Why was this designed this way?"
4. Answer with: ADR + commit + code
5. Highlight:
   - Undocumented components
   - Generated documentation

---

## ⚠️ Critical Integration Rules (Do NOT Ignore)

1. **Define a shared data schema early**
   - If you don't, everything breaks later.

2. **Sync twice a week**
   - Not optional.

3. **Don't overbuild early**
   - No perfect NER
   - No perfect graph
   - No perfect UI

4. **Always keep a working pipeline**
   - Even if it's: dumb but functional

---

## 🧠 Ownership Matrix

| Area | Owner |
|------|-------|
| Ingestion | Utkrisht |
| Code parsing | Utkrisht |
| Entity extraction | Utkrisht |
| Embeddings | Harsh |
| Retrieval | Harsh |
| Q&A | Harsh |
| Graph | Shared (led by Utkrisht) |
| Linking | Shared |
| Gap detection | Harsh |

---

## 🔥 Getting Ahead of Everyone

**Do this one thing:**

👉 **By end of Sprint 2, have:**
- Retrieval ✓
- Basic Q&A ✓
- Partial linking ✓

Most teams won't even have ingestion done by then.

---

## 👍 Final Takeaway

**Your success depends on:**
- ✅ Early integration
- ✅ Simple first version
- ✅ Iterative improvements

**NOT on:**
- ❌ Fancy models
- ❌ Perfect extraction

---

## 📌 Key Dates & Milestones

- **End of Sprint 1 (Week 1):** Basic end-to-end retrieval system
- **End of Sprint 2 (Week 2):** Q&A + entity linking working
- **End of Sprint 3 (Week 3):** Knowledge graph + "why" reasoning
- **End of Sprint 4 (Week 4):** Production-ready demo with gap detection & generated docs

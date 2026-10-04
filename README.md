## Data
- Fannie Mae Selling Guide, published September 2, 2026 (1,196 pages),
  downloaded from selling-guide.fanniemae.com.
  Not included in this repo due to licensing; download it and place it
  in data/raw/selling_guide.pdf.

## Retrieval experiments

Setup: 123 rules from Part B3 split into 401 chunks (1,500 chars, 200 overlap,
with contextual headers), embedded with BAAI/bge-small-en-v1.5, stored in Qdrant.
Evaluated on 20 everyday-language questions with known target rules.

| Method                          | Hit@1 | Hit@3 | Hit@5 |
|---------------------------------|-------|-------|-------|
| Baseline (original question)    | 85%   | 95%   | 100%  |
| + BGE query instruction         | 85%   | 95%   | 100%  |
| LLM query rewriting             | 85%   | 90%   | 95%   |
| Rank fusion (original + rewrite)| 80%   | 95%   | 100%  |

Findings: no technique significantly beat the baseline on this test set
(one question = 5%). Rewriting fixed vocabulary-gap questions
("parents" -> "gift funds") but broke others by introducing jargon the guide
doesn't use ("consummation" vs. "note date"). Kept the simpler baseline;
adaptive query reformulation will be handled by the agent.

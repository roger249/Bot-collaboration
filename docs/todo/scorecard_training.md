1. Pairwise Logistic Ranking (best first choice)
- Train on judgments like “A should rank above B” for same client.
- Very data-efficient.
- Easy to regularize and explain.
- Works with your current score components as features.

2. Bradley-Terry / Plackett-Luce (if labels are mostly preference/order)
- Great when you have partial rankings or top-k choices.
- Cleaner probabilistic interpretation than ad hoc weighting.
- Good with limited samples.

3. RankSVM (if you want max-margin behavior)
- Strong for pairwise ranking.
- Usually robust, but less interpretable than logistic unless carefully documented.

4. Bayesian logistic ranking (if data is very small)
- Put priors around weights to prevent overfitting.
- Gives uncertainty bands, useful for governance.
- Slower, but safer when samples are tiny.

Practical recommendation:
- Start with pairwise logistic + L2 regularization.
- Use hard gates as fixed business rules, and train only the soft ranking weights.
- Retrain quarterly, not monthly, unless you have enough new labeled comparisons.

I'd like to generalize the current prompts to the planbot for use in areas other than private banking.  First steps is restructure the prompt construction as below.

- major prompts resides in crewai agents and tasks.yaml
- The crewai.yaml will refer to a set of reference data such as client profile, product catalog that will be submitted in a JSON format as it is, listed in the config/config_planbot.yaml under the section product_investor_matching.reference.
- The changes will be extended to all reports in config_planbot.yaml
- The JSON will be constructed such that the files listed under the section heading (e.g., guidelines) will be submitted in a JSON block of same name.  This should be similar to the current, but now the headings are read from the config_planbot.yaml
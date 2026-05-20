# Objective

To introduce a tool to retrieve website content so that LLM could provide financial advise based on the latest data

We'll use the FirecrawlScrapeWebsiteTool for ths purpose.

A sample new agent has added to the data/planbot/stock_analysis/crewai/agents.yaml for create this agent when required.

```yaml
senior_research_analyst:
    role: >
        Senior Research Analyst
    goal: >
        Extract and structure deep data from targeted web pages
    backstory: >
        An expert at extracting underlying insights from dense target articles.
    tools: [FirecrawlScrapeWebsiteTool]
```    

# Acceptance criteria
- The LLM (from POE) could make use of this tool when it requires to search a website.  
- The above action will be triggered by a user prompt that ask the LLM for the stock price as of today.

# Development guideline
Please observe docs/prompts/developer_guidelines.md for this feature
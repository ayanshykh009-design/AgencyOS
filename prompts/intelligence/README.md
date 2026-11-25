# Intelligence prompts (M9 Founder Intelligence)

Versioned prompts used by the M9 founder intelligence layer. Render via
`app.llm.prompts.PromptManager` (`name@version`), never by string-building in
business logic.

| Prompt | Version | Purpose |
| ------ | ------- | ------- |
| `intelligence-narrative` | 1.0.1 | Grounded plain-text digest of the top triaged signals; renders the bounded `signalsJson` context (1.0.0 is deprecated) |

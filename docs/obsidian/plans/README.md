---
tags: [catan, планы]
---

# Engineering plans

[[00 Главная]] · [[Project State]] · [[Documentation Policy]]

Крупная задача имеет отдельный план с целью, областью, инвариантами, шагами и проверкой. План не является разрешением на изменение кода. Начать исполнение можно только в рамках соответствующей задачи пользователя.

- [[plans/server-authority-hardening]] — Phase 1 завершена 2026-10-03 после исходных проверок 2026-10-02; оставшиеся ограничения указаны в плане.
- [[plans/web-ui-redesign]] — исторический первоначальный Draft/reference plan; текущую реализацию описывает [[plans/game-ui-redesign]].
- [[plans/game-ui-redesign]] — Game UI Phases 1/2, Room UX 2.1–2.3 и Product Polish Phases 1–4 завершены в своём scope, включая audio; future mobile/accessibility/load work явно отделены.
- [[plans/containerization]] — Production Infrastructure Phase 1 Completed, 2026-10-04; эксплуатационные инструкции — [[Deployment]].
- [[plans/board3d]] — Phases 1–3/polish и terrain/building GLB integration завершены. Default 3D и SVG используют один snapshot/controller; interactive renderer не исполняет правила.
- [[plans/seafarers-s1]] — historical completed S1, проверен 2026-10-08; S1/F1/F2/F3 checkpoint `seafarers-hardening-s1` → `b5cc066`.
- [[plans/seafarers-s2a]] — maps/islands/coasts/ports и no-desert robber завершены и проверены 2026-10-09; checkpoint commit `e79dee4`. Tag optional, не блокирует development.
- [[plans/seafarers-s2b-1]] — historical completed explicit custom scenario start/bonus/capacity/VP, codec v3 и provenance, 2026-10-09; позднейшие codec/provenance статусы отмечены в плане. Existing custom presets сохранены; public Fog/S2C и более широкая natural-match acceptance остаются future work.
- [[Карты и сценарии#Official Heading for New Shores — S3A]] и [[Карты и сценарии#Official The Four Islands — S3B]] — official Scenarios 1/2 реализованы на общем S2B-1 executor/ledger: точные 2021 3-/4-player layouts, edition-specific rules/provenance. S3B опубликован как `dfd6c04`; executed suites/browser/natural matches — [[Project State]]. Сценарии 3–9 и variable setup не реализованы.
- [[plans/seafarers-fog]] — foundation `0fa8f6d`, exploration `1b41360`, secure projection `dc121da`, rendering и live integration `d6f94a1`. Natural full-match follow-up 2026-10-17 проверяет empty setup→legal production/build/discovery→victory→recovery/rematch через тот же TCP/PostgreSQL/F1 flow; admission только в guarded test process. **Public Fog DISABLED**; activation phases записаны как design-only, broader natural/competitive/player-count coverage не заявлена. Фактические финальные checks — [[Project State]].
- [[plans/persistence-auth]] — Persistence 1A/1B/1C, Auth Phase 1 и F2 safe legacy restriction завершены; profiles/history/reset и Strategy D conversion planned, не реализованы.
- [[Сервер и протокол#Private publication authorization — F1]] и [[Desktop клиент#Ship lifecycle persistence — F3]] — узкие fixes завершены; отдельные дублирующие планы не создавались.
- [[plans/plan-template]] — форма для новой крупной задачи; сначала проверить отсутствие существующего плана.

По завершении план можно сохранить как инженерную историю; актуальное состояние всегда обновляется в Project State. Не записывать переписку и ежедневные логи.

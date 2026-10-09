---
tags: [catan, правила, спецификация]
---

# Правила Seafarers

## Explicit starting islands and special VP — S2B-1

**Implemented/tested 2026-10-09, custom opt-in only.** Existing Coastal Lanes, Sea Ring, Gold Haven and Pirate Lanes do not enable start restrictions or island VP; their target remains 10 unless overridden by the host. These are custom layouts, not official scenario replicas. The [official rulebook](https://www.catan.com/sites/default/files/2021-06/catan-seafarers_2021_rule_book_201201.pdf) describes different bonus/target policies per scenario; Heading for New Shores's main-island/+2/14 VP policy is not silently assigned to this project's maps.

An explicitly configured custom `rules.scenario.starting_islands` restricts setup settlements to those land components and prevents openings that leave insufficient distance-rule positions for remaining placements. Missing/null is unrestricted. Anchored initial road/ship choices remain. `new_island_vp` explicitly sets 0..10 extra VP (0/missing disables it), not a universal +2 assumption.

When enabled, each player's actual setup islands are recorded as home islands. Accepted main-phase first settlement on each other island awards the configured bonus in addition to ordinary 1 VP. Another player's earlier arrival does not remove eligibility; repeated settlements/city upgrades do not award again. Setup never awards it. The ledger is durable and public; special VP is already included in total VP. Existing hidden VP privacy, Longest Trade Route scoring and own-turn victory checks remain. Recovery restores the ledger and never recalculates awards/VP. Details — [[plans/seafarers-s2b-1]], [[Состояние игры#Scenario persistence — S2B-1]].

**Historical S2B-1 limitation, subsequently fixed 2026-10-09:** `update_largest_army` used to clear a tied incumbent and remove its 2 VP. The focused Largest Army patch now retains a qualified holder on ties and transfers only to a strictly stronger army, with unchanged own-turn victory timing. Base/Seafarers and an already-awarded scenario ledger are covered separately; recovery never recalculates historical awards/scores. Results — [[Project State#Largest Army tie handling — focused correctness fix]]. Fog/exploration and unapproved per-preset product rules remain future work.

## Maps/coastlines and initial figures — S2A, 2026-10-09

**Implemented/tested.** Gold Haven и Pirate Lanes теперь имеют два раздельных playable land components с navigable sea; Coastal Lanes/Sea Ring намеренно остаются одноостровными. Room поддерживает 2–6 игроков, обычный setup может ставить settlement на любой legal land vertex, затем anchored road или ship. Ни один preset не объявляет starting region; S2A не добавляет запрет поселиться на другом острове или бонус за него. Дистанция/cost/supply/ownership и ship-turn rules остаются в общем executor S1.

Порты новых карт находятся на land↔sea/frame coastline и не делят endpoints. Своя settlement/city на исходном port endpoint даёт generic 3:1 либо specialized 2:1 как прежде. Derived island IDs не дают очков и не передаются новым state полем. Карты/decks/counts/проверка — [[Карты и сценарии]], [[plans/seafarers-s2a]].

Seafarers без desert начинает с `robber_tile=-1` (вне board), согласно [официальному Seafarers FAQ](https://www.catan.com/faq/seafarers). После Seven/discard либо Knight игрок выбирает одну допустимую фигуру. Первый robber move ставит его на настоящий land tile; выбор pirate оставляет robber offboard. Pirate начинается только на sea. Gold Haven имеет -1 и не блокирует произвольный Gold при старте; Pirate Lanes содержит одну desert. -1 не принимается как command target. SVG/Three/Qt не рисуют offboard фигуру; trusted v2 сохраняет её, frozen v1 не получает нового domain. Historical saved positions/maps не переписываются.

Full pytest **823**, web **250**, TypeScript/build; real two-client Gold Haven/Pirate Lanes acceptance включил setup/Gold/ships, funded expansion и Seven/Knight. Это focused flows/fixtures, не полный natural match и не сертификация arbitrary custom maps. S2B: scenario start islands/rewards/fog; S2C: последующая customization/balance по отдельной задаче; S3: полные партии/широкие clients и оставшиеся core limitations.

## Core implementation verified — S1, 2026-10-08

Existing rules were hardened against the user specification and [official Seafarers FAQ](https://www.catan.com/faq/seafarers)/[2025 rulebook](https://www.catan.com/sites/default/files/2025-03/CN3083%20CATAN%E2%80%93Seafarers%20Rulebook%202025%20secured%20reduced.pdf). No new expansion or universal scenario bonus was introduced.

- Ship placement requires a sea/coastal edge, free occupancy and an own building or own ship connection; a foreign building blocks extension. Road↔ship transitions need an own settlement/city.
- Initial route may be an anchored free ship. Road Building credits support ships/roads/mixed placement in the current turn and expire on End Turn as already approved.
- One old open ship may move during an ordinary action phase to any legal new ship placement, checked after excluding its source. Newly constructed ships, closed lines and pirate-adjacent sources/targets cannot move. Official circular-shipping exceptions are handled; foreign buildings do not reopen a closed line. Trade-route blocking and maritime closure are different questions.
- Longest Trade Route counts a maximum continuous edge trail over roads/ships; branches are not simply added, edges cannot repeat. Own buildings permit changes of piece kind; opponent buildings interrupt the trail. The existing ≥5/2VP award retains a qualified tied incumbent and transfers only to a stronger eligible route. Final movement state determines ownership; victory waits for the winner's own turn.
- A connected ship permits a coastal destination-island settlement with ordinary costs, piece supply and distance rule. Core scoring grants only its ordinary 1VP; start-island discovery rewards require explicit scenario rules.
- Gold produces one manual choice per settlement or two per city, supports different chosen resources, and is blocked by robber. Second-settlement setup Gold is a mandatory choice before the initial route. Empty/exhausted bank cannot leave an impossible pending obligation; unavailable requested quantities reject atomically. Existing numeric recipient queue is preserved, not presented as an official scarcity arbitration policy.

Seven/Knight still create one robber-or-pirate choice after required discards; land/sea/current tile/victim checks precede mutation. One accepted figure move allows at most one theft, then clears pending; nonparticipants see no stolen resource type. Theft's existing deterministic selection is unchanged and remains separate gameplay work.

**Historical S1 scope:** production archipelagos/coastal ports/offboard initialization тогда оставались S2, а two-island mechanics проверялись через [test_seafarers_islands.py](../../tests/test_seafarers_islands.py). Они реализованы в S2A выше. Bonuses/fog/exploration и утверждённые scenario start zones остаются future work; natural matches, scarce Gold arbitration/card sequencing и broader clients тоже не объявляются завершёнными. Исходное S1 доказательство — [[plans/seafarers-s1]].

Источник: [[Спецификация пользователя]]. Дополнение сохраняет [[Правила Base Game]], если механика или сценарий их явно не переопределяет.

| Механика | Требование |
| --- | --- |
| Корабль | 1 wood + 1 sheep; допустимое морское ребро; связь со своей прибрежной постройкой либо концом допустимого морского маршрута |
| Смешанные маршруты | Дорога и корабль обычно соединяются через свою прибрежную постройку |
| Перемещение | Только подходящий открытый конечный корабль; часть закрытого маршрута перемещать нельзя |
| Острова | Достижение допустимой вершины позволяет строить с обычными ограничениями; бонусы задаёт сценарий |
| Золото | По выпавшему номеру даёт выбор стандартного ресурса; не является шестым ресурсом |
| Пират | Морская клетка; блокировки и события движения задаёт сценарий; отдельная механика от разбойника |
| Longest Trade Route | Учитывает дороги/корабли и топологию; чужие поселения могут прерывать маршрут |
| Fog / exploration | Открытие клеток и награды определяет сценарий |

Спецификация не задаёт все численные ограничения перемещения и детали каждого сценария. Нельзя дополнять её произвольными универсальными правилами: нужен выбранный сценарий и его ограничения.

Сценарий может задавать карту, числа, стартовые острова, скрытые клетки, пирата, особые очки, целевой VP, токены, exploration-награды и дополнительные цели.

В коде смотри RulesConfig, can_place_ship и ветки build_ship/move_ship/move_pirate/choose_gold в [[Игровой движок]]. Пресеты и параметры — [[Карты и сценарии]]. Текущие расхождения — [[Результаты аудита]].

## Pirate event lifecycle

Уточнение существующего требования спецификации: пират перемещается при событии, требующем движения robber-type piece, если это разрешено сценарием. Свободное многократное движение с кражей в обычный ход не является таким событием.

Текущая реализация проверена 2026-10-02: 7 → обязательные discard, если нужны → pending `robber_move`; Knight создаёт тот же pending, в том числе до броска. `RulesConfig.enable_pirate` разрешает выбрать **одну** фигуру: разбойника на другой land hex либо пирата на другой sea hex. `pending_pid` определяет игрока, которому принадлежит выбор.

Victim проверяется до изменения состояния. Для разбойника используются соседние постройки; для пирата — соседние корабли других игроков с непустой рукой. Если victim не передан, текущий engine выбирает первого допустимого игрока; при отсутствии жертв движение завершается без кражи. Перемещение и максимум одна кража выполняются одной командой, после чего pending_action/pending_pid/pending_victims очищаются. Отдельной команды pirate theft нет. Новый trigger может разрешить новое движение, в том числе в том же ходу; лимит привязан к событию, а не произвольному числу движений за ход.

Имя `robber_move` и формат snapshot сохранены. React/PySide при этом pending выбирают фигуру по land/sea клику. Эти детали описывают поддерживаемые пресеты, не добавляют правила иных сценариев; специальные требования сценариев нужно проверять отдельно. Алгоритм выбора украденного ресурса в этом исправлении не менялся.

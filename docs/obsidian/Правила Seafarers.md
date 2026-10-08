---
tags: [catan, правила, спецификация]
---

# Правила Seafarers

## Core implementation verified — S1, 2026-10-08

Existing rules were hardened against the user specification and [official Seafarers FAQ](https://www.catan.com/faq/seafarers)/[2025 rulebook](https://www.catan.com/sites/default/files/2025-03/CN3083%20CATAN%E2%80%93Seafarers%20Rulebook%202025%20secured%20reduced.pdf). No new expansion or universal scenario bonus was introduced.

- Ship placement requires a sea/coastal edge, free occupancy and an own building or own ship connection; a foreign building blocks extension. Road↔ship transitions need an own settlement/city.
- Initial route may be an anchored free ship. Road Building credits support ships/roads/mixed placement in the current turn and expire on End Turn as already approved.
- One old open ship may move during an ordinary action phase to any legal new ship placement, checked after excluding its source. Newly constructed ships, closed lines and pirate-adjacent sources/targets cannot move. Official circular-shipping exceptions are handled; foreign buildings do not reopen a closed line. Trade-route blocking and maritime closure are different questions.
- Longest Trade Route counts a maximum continuous edge trail over roads/ships; branches are not simply added, edges cannot repeat. Own buildings permit changes of piece kind; opponent buildings interrupt the trail. The existing ≥5/2VP award retains a qualified tied incumbent and transfers only to a stronger eligible route. Final movement state determines ownership; victory waits for the winner's own turn.
- A connected ship permits a coastal destination-island settlement with ordinary costs, piece supply and distance rule. Core scoring grants only its ordinary 1VP; start-island discovery rewards require explicit scenario rules.
- Gold produces one manual choice per settlement or two per city, supports different chosen resources, and is blocked by robber. Second-settlement setup Gold is a mandatory choice before the initial route. Empty/exhausted bank cannot leave an impossible pending obligation; unavailable requested quantities reject atomically. Existing numeric recipient queue is preserved, not presented as an official scarcity arbitration policy.

Seven/Knight still create one robber-or-pirate choice after required discards; land/sea/current tile/victim checks precede mutation. One accepted figure move allows at most one theft, then clears pending; nonparticipants see no stolen resource type. Theft's existing deterministic selection is unchanged and remains separate gameplay work.

S2: actual multi-island presets/start islands, bonuses/fog/exploration, coastal ports, and no-desert initial robber offboard handling. S3: complete natural matches, scarce Gold arbitration/card sequencing and broader clients. Current presets remain one land component; actual two-island geometry is tested only in [test_seafarers_islands.py](../../tests/test_seafarers_islands.py). Exact proof and limitations — [[plans/seafarers-s1]].

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

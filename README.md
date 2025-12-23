# CATAN-GAME (Base + LAN)

Это реализация "по механикам как Catan" (без официальных артов/материалов).

## Запуск
### Сервер (на хосте)
.\run_server.ps1 -Port 8000

IP хоста: ipconfig -> IPv4.

### Клиенты (на каждом ПК)
.\run_client.ps1 -HostIP 192.168.1.10 -Port 8000 -Room room1 -Name Alice
.\run_client.ps1 -HostIP 192.168.1.10 -Port 8000 -Room room1 -Name Bob

Если Firewall спросит доступ — разреши Private network.

## Команды клиента
help
state
start [seed]                      (host only)

# setup
place <node> <edge>

# main
roll
discard wood=1 brick=0 wheat=0 sheep=0 ore=0     (если попросит сбросить)
robber <hex> [victimId]                           (после 7)

build road <edge>
build settlement <node>
build city <node>

trade bank give=wood:4 get=ore                    (порт/4:1 учтётся автоматически)

buy dev

play knight <hex> [victimId]
play road <edge1> <edge2>                         (Road Building)
play monopoly <res>
play plenty <res1> <res2>

end
quit

Подсказки (валидные node/edge и т.п.) показываются в Hints.

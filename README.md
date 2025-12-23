# CATAN-GAME (Desktop + LAN Multiplayer)

## Run server
.\run_server.ps1 -Port 8000

## Run desktop client
.\run_desktop.ps1 -HostIP 127.0.0.1 -Port 8000 -Room room1 -Name Alice
.\run_desktop.ps1 -HostIP 127.0.0.1 -Port 8000 -Room room1 -Name Bob

### Notes
- In browser you open: http://127.0.0.1:8000/ (NOT 0.0.0.0)
- Gameplay:
  - Host presses Start
  - Setup: place settlement+road twice (snake order) via clicks + Place button
  - Main: Roll, Build, Trade, End

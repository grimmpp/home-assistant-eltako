docker run -d --name home-assistant --restart unless-stopped -v C:\Users\User\Documents\homeassistant:/config -e "TZ=America/New_York" -p 8123:8123 -p 5678:5678 homeassistant/home-assistant:latest
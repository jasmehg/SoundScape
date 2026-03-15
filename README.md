# SoundScape
SMATH Hackathon 2026
## Inspiration
The inspiration for this project came from researching ocean pollution for the hackathon. I always associated ocean pollution with things you could see, like plastic and oil spills. What I didn't realize was that there's another kind of pollution that's completely invisible: noise. Ships are incredibly loud underwater. Because sound travels so much faster in water than in air, that noise doesn't just fade out nearby. It spreads for hundreds of miles. Whales depend on sound for almost everything. They use it to navigate, communicate, and find food. When background noise gets loud enough, around 118 decibels, they lose that ability. They get disoriented and wander off their migration routes. I found this genuinely shocking and wanted to build something that showed people how it works.
## What it does
SoundScape is a real-time simulation where you play as an ocean traffic manager trying to guide six whale pods safely through a busy shipping corridor. Five ships travel vertically through the ocean, crossing three horizontal whale migration lanes. Each ship constantly generates noise based on its speed. If you do nothing, the noise overwhelms the whales, their stress bars fill from green to yellow they lose navigation.
You have two tools. You can drag a ship left or right to permanently reroute it away from the whale lanes, and you can click a ship to slow it down since slower propellers produce less noise. The goal is to get all six whales safely across before they strand.
## How it was built
The project was built using Pygame. The core components include:
**Ship class**: Each ship has a permanent lane position that the player changes by dragging. The ship smoothly slides to its new lane and respawns there after every pass, so rerouting is actually permanent and not just temporary.
**Whale class**: Each whale calculates its total noise exposure every frame by summing contributions from all five ships. That noise level drives the stress system. Above 118 dB, stress builds. Drop below 100 dB and it recovers.
**Acoustic physics**: The noise calculations use the underwater acoustic transmission loss formula.
## Challenges
Tuning the stress rates: Ships are genuinely very loud in real life, which meant my first version had whales stranding within seconds of starting. Getting the stress build and recovery rates balanced so players had enough time to react but couldn't just ignore everything took a lot of iteration. I ran the math outside the game to simulate different scenarios before putting numbers back in.
## What I learned
This project taught me a lot about how to build physics simulations where the numbers actually matter for gameplay. Managing multiple objects with their own state got complicated fast when dragging, slowing, and stress all needed to interact without breaking each other.
I also came away knowing a lot more about ocean noise than I expected. The explained code is in the jupyter notebook.

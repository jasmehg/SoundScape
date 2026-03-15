import pygame
import math
import random
import sys

pygame.init()

# window setup
width, height = 1500, 750
win = pygame.display.set_mode((width, height))
pygame.display.set_caption("SoundScape")

# ocean is left side, info panel is right side
OCEAN_W = 700

FPS = 60

# the 3 horizontal lanes whales travel along (y positions)
# ships cross vertically and some start right on these lanes -- thats the problem
WHALE_LANES = [115, 325, 535]
SHIP_STARTS = [100, 220, 325, 470, 610] #3 of these overlap whale lanes intentionally

# colors
OCEAN   = (8,  48, 66)
PANEL   = (14, 22, 34)
AMBER   = (215, 158, 44)
TEAL    = (75, 158, 118)
WHITE   = (228, 222, 205)
GRAY    = (118, 114, 102)
GREEN   = (58,  178, 115)
YELLOW  = (210, 165, 40)
RED     = (198, 55,  46)
FOAM    = (155, 205, 195)

font1 = pygame.font.SysFont("Trebuchet MS", 21, bold=True) #big values
font2 = pygame.font.SysFont("Trebuchet MS", 15) #medium
font3 = pygame.font.SysFont("Trebuchet MS", 12)  #small labels
font4 = pygame.font.SysFont("Trebuchet MS", 11, bold=True) #key badges

# ocean background once so we dont redraw every frame (performance fix)
ocean_bg = pygame.Surface((OCEAN_W, height))
for y in range(height):
    f = y / height
    pygame.draw.line(ocean_bg, (int(8+f*5), int(48+f*16), int(66+f*7)), (0, y), (OCEAN_W, y))

# NOAA underwater acoustic transmission loss formula:
# TL = 20 * log10(distance_meters) + 0.0008 * distance_meters
# received noise = source_db - TL
# whales lose navigation above 18dB 
def received_db(source_db, dist_px):
    m = max(1.0, dist_px * 10) #1 pixel = 10 meters in this sim
    tl = 20 * math.log10(m) + 0.0008 * m #transmission loss
    return max(0.0, source_db - tl)


class Ship:
    def __init__(self, x, slot=0, start_y=None):
        self.lane = float(x)
        self.x    = float(x)
        self.y    = float(start_y if start_y is not None else -80 - slot * 55)
        self.speed      = 0.7 + (slot % 3) * 0.15
        self.base_speed = self.speed
        self.is_slow        = False
        self.being_dragged  = False
        self.wake_trail     = []
        self.finished       = False

    @property
    def noise_db(self):
        #slower propellers = less cavitation = quieter
        speed_ratio = self.speed / self.base_speed
        return 168.0 * (0.60 + 0.40 * speed_ratio)

    def get_danger_radius(self):
        #find pixel distance where noise drops to 118dB (masking threshold)
        #binary search because solving analytically with the alpha term is annoying
        lo, hi = 1.0, 450.0
        for _ in range(15):
            mid = (lo + hi) / 2.0
            if received_db(self.noise_db, mid) > 118:
                lo = mid
            else:
                hi = mid
        return lo

    def update(self):
        if self.finished:
            return
        if not self.being_dragged:
            self.x += (self.lane - self.x) * (1/60) * 4 #slide toward lane_x smoothly
            self.y += self.speed * (1/60) * 60
        self.wake_trail.append((int(self.x), int(self.y)))
        if len(self.wake_trail) > 22:
            self.wake_trail.pop(0)
        if self.y > height + 40:
            self.finished = True

    def toggle_slow(self):
        self.is_slow = not self.is_slow
        self.speed = self.base_speed * (0.28 if self.is_slow else 1.0)

    def check_click(self, mx, my):
        return abs(self.x - mx) < 24 and abs(self.y - my) < 24

    def draw(self):
        if self.finished:
            return
        #draw wake
        for i, (wx, wy) in enumerate(self.wake_trail):
            alpha = int(38 * i / max(len(self.wake_trail), 1))
            s = pygame.Surface((4, 4), pygame.SRCALPHA)
            pygame.draw.circle(s, (*FOAM, alpha), (2, 2), 2)
            win.blit(s, (wx - 2, wy - 2))
        #draw ship hull (pointing downward)
        cx, cy = int(self.x), int(self.y)
        col = AMBER if self.is_slow else (85, 92, 105)
        hull = [(cx, cy-16), (cx+9, cy-5), (cx+7, cy+12), (cx-7, cy+12), (cx-9, cy-5)]
        pygame.draw.polygon(win, col, hull)
        pygame.draw.polygon(win, (190, 196, 206), hull, 1)
        pygame.draw.rect(win, (100, 106, 118), (cx-4, cy-5, 8, 13))
        pygame.draw.circle(win, (252, 234, 168), (cx, cy), 3) #nav light
        if self.is_slow:
            lb = font3.render("SLOW", True, AMBER)
            win.blit(lb, (cx - lb.get_width() // 2, cy - 30))


class Whale:
    whale_count = 0
    def __init__(self, lane_y, start_x=None):
        self.lane_y = float(lane_y)
        self.x = float(start_x if start_x is not None else -1 * random.randint(20, 60))
        self.y = float(lane_y + random.randint(-12, 12))
        self.vx = 0.0
        self.vy = 0.0
        self.stress  = 0.0
        self.is_lost  = False
        self.is_safe  = False
        self.is_stranded  = False
        self.wander_angle = 0.0
        self.trail  = []
        self.counted_strand = False
        self.counted_safe = False
        Whale.whale_count  += 1

    def get_noise_level(self, ships):
        #sum acoustic intensities from all ships (cant just average dB values)
        total_intensity = 0.0
        for s in ships:
            if s.finished:
                continue
            dist = math.sqrt((self.x - s.x)**2 + (self.y - s.y)**2)
            db = received_db(s.noise_db, dist)
            total_intensity += 10.0 ** (db / 10.0) #convert to linear, add, convert back
        return 10.0 * math.log10(total_intensity) if total_intensity > 0 else 0.0

    def move(self, ships):
        if self.is_stranded or self.is_safe:
            return

        noise = self.get_noise_level(ships)

        #stress builds when loud, recovers when quiet
        #tuned so player has about 15s before whale goes lost
        if noise > 118:
            self.stress = min(1.0, self.stress + (1/60) * 0.07)
        elif noise > 100:
            self.stress = min(1.0, self.stress + (1/60) * 0.01)
        else:
            self.stress = max(0.0, self.stress - (1/60) * 0.12)

        self.is_lost = self.stress > 0.55

        if self.is_lost:
            #wander randomly, gets wilder the more stressed
            chaos = 0.5 + self.stress
            self.wander_angle += random.gauss(0, dt * chaos)
            self.wander_angle  = max(-1.3, min(1.3, self.wander_angle))
            target_vx = math.cos(self.wander_angle) * 0.44
            target_vy = math.sin(self.wander_angle) * 0.44
        else:
            #swim toward the right side, gently correct back to lane_y
            dx = (OCEAN_W + 10) - self.x
            dy = self.lane_y - self.y
            dist = math.sqrt(dx**2 + dy**2) + 0.001
            target_vx = (dx / dist) * 0.47
            target_vy = (dy / dist) * 0.47 * 0.28 #0.28 so y correction is gentle

        smooth = min(1.0, (1/60) * 3.5)
        self.vx += (target_vx - self.vx) * smooth
        self.vy += (target_vy - self.vy) * smooth
        self.x  += self.vx
        self.y  += self.vy

        #strand if VERY stressed and hits an edge
        edge = 18
        if self.stress > 0.72 and self.is_lost:
            if self.y < edge or self.y > height - edge or self.x < edge:
                self.is_stranded = True
                return

        self.y = max(edge, min(height - edge, self.y)) #soft clamp
        self.x = max(-80, self.x)

        if self.x > OCEAN_W - 8: #made it across!
            self.is_safe = True
            return

        self.trail.append((int(self.x), int(self.y)))
        if len(self.trail) > 38:
            self.trail.pop(0)

    def draw(self):
        #trail color changes when lost
        trail_col = RED if self.is_lost else TEAL
        for i, (tx, ty) in enumerate(self.trail):
            alpha = int(40 * i / max(len(self.trail), 1))
            s = pygame.Surface((4, 4), pygame.SRCALPHA)
            pygame.draw.circle(s, (*trail_col, alpha), (2, 2), 2)
            win.blit(s, (tx - 2, ty - 2))

        cx, cy = int(self.x), int(self.y)
        ang = math.atan2(self.vy, self.vx) if (self.vx or self.vy) else 0
        ca, sa = math.cos(ang), math.sin(ang)

        def rot(px, py): #rotate point around whale center
            return (cx + int(px*ca - py*sa), cy + int(px*sa + py*ca))

        #body color gets redder the more stressed
        bc = (min(255, int(50 + self.stress*60)),
              max(0, int(72 - self.stress*26)),
              max(0, int(92 - self.stress*30)))

        pygame.draw.polygon(win, bc, [rot(-25,0), rot(-18,7), rot(-14,3), rot(-14,-3), rot(-18,-7)]) #tail
        pygame.draw.polygon(win, bc, [rot(24,0), rot(14,7), rot(0,9), rot(-12,7), rot(-24,0), rot(-12,-7), rot(0,-9), rot(14,-7)]) #body
        pygame.draw.polygon(win, (112, 138, 155), [rot(16,0), rot(7,4), rot(-6,5), rot(-14,0), rot(-6,-5), rot(7,-4)]) #belly
        pygame.draw.polygon(win, bc, [rot(7,7), rot(0,16), rot(-8,13), rot(-3,8)]) #pec fin

        ex, ey = rot(12, -3)
        pygame.draw.circle(win, (205, 210, 220), (ex, ey), 3) #eye white
        pygame.draw.circle(win, (14,  14,  22),  (ex, ey), 2) #pupil

        if self.is_stranded: #X mark
            pygame.draw.line(win, RED, (cx-9, cy-9), (cx+9, cy+9), 3)
            pygame.draw.line(win, RED, (cx+9, cy-9), (cx-9, cy+9), 3)

        if not self.is_stranded and not self.is_safe: #stress bar above whale
            bw = 34
            bx = cx - bw // 2
            by = cy - 32
            pygame.draw.rect(win, (14, 22, 32), (bx-1, by-1, bw+2, 7), border_radius=2)
            t = (self.stress / 0.5) if self.stress < 0.5 else (self.stress - 0.5) / 0.5
            c1 = GREEN if self.stress < 0.5 else YELLOW
            c2 = YELLOW if self.stress < 0.5 else RED
            bar_col = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
            fw = int(bw * self.stress)
            if fw > 0:
                pygame.draw.rect(win, bar_col, (bx, by, fw, 5), border_radius=2)
            if self.stress > 0.4:
                lb = font3.render("LOST!" if self.is_lost else "stressed", True, bar_col)
                win.blit(lb, (cx - lb.get_width() // 2, by - 13))


def draw_noise_rings(ships, t):
    #expanding rings show how far each ships noise reaches
    ring_surf = pygame.Surface((OCEAN_W, height), pygame.SRCALPHA)
    for s in ships:
        if s.finished:
            continue
        dr = s.get_danger_radius()
        for i in range(3):
            phase = ((t * 0.45) + i * 0.333) % 1.0
            rad = phase * dr
            if rad < 4:
                continue
            alpha = int(72 * (1.0 - phase))
            db_here = received_db(s.noise_db, rad)
            ring_col = RED if db_here > 125 else YELLOW if db_here > 110 else GREEN
            pygame.draw.circle(ring_surf, (*ring_col, alpha), (int(s.x), int(s.y)), int(rad), 2)
    win.blit(ring_surf, (0, 0))


def draw_panel(whales, score, safe_count, strand_count, msg, msg_timer, hovered_ship):
    pygame.draw.rect(win, PANEL, (OCEAN_W, 0, width - OCEAN_W, height))
    pygame.draw.line(win, (34, 68, 82), (OCEAN_W, 0), (OCEAN_W, height), 2)

    lx = OCEAN_W + 14
    uw = width - OCEAN_W - 28
    y  = 14

    win.blit(font1.render("SoundScape", True, AMBER), (lx, y));  y += 28
    win.blit(font3.render("Ocean Noise Simulator", True, GRAY),  (lx, y));  y += 18
    pygame.draw.line(win, (34, 68, 82), (lx, y), (width - 14, y), 1);  y += 10

    for label, val, col in [("Safe", str(safe_count),  GREEN),
                              ("Stranded", str(strand_count), RED if strand_count else GRAY),
                              ("Score",    str(score),        AMBER)]:
        win.blit(font3.render(label, True, GRAY),  (lx, y));   y += 13
        win.blit(font1.render(val,   True, col),   (lx, y));   y += 26
    y += 4
    pygame.draw.line(win, (34, 68, 82), (lx, y), (width - 14, y), 1);  y += 10

    win.blit(font4.render("WHALE STRESS", True, (115, 85, 18)), (lx, y));  y += 17
    for i, w in enumerate(whales):
        if w.is_safe:       st, col = "safe",     GREEN
        elif w.is_stranded: st, col = "stranded",  RED
        elif w.is_lost:     st, col = "LOST!",     RED
        elif w.stress > 0.35: st, col = "stressed", YELLOW
        else:               st, col = "ok",        GREEN
        win.blit(font3.render(f"Whale {i+1}  {st}", True, col), (lx, y))
        pygame.draw.rect(win, (18, 28, 40), (lx, y+13, uw, 5), border_radius=2)
        fw = int(uw * w.stress)
        if fw > 0:
            pygame.draw.rect(win, col, (lx, y+13, fw, 5), border_radius=2)
        y += 24

    y += 4
    pygame.draw.line(win, (34, 68, 82), (lx, y), (width - 14, y), 1);  y += 10

    if hovered_ship and not hovered_ship.finished:
        win.blit(font3.render(f"Noise: {hovered_ship.noise_db:.0f} dB", True, WHITE), (lx, y));  y += 14
        win.blit(font3.render("slowed" if hovered_ship.is_slow else "full speed", True,
                               AMBER if hovered_ship.is_slow else WHITE), (lx, y));  y += 18
        pygame.draw.line(win, (34, 68, 82), (lx, y), (width - 14, y), 1);  y += 10

    win.blit(font4.render("CONTROLS", True, (115, 85, 18)), (lx, y));  y += 17
    for key, desc, bc in [("DRAG", "reroute ship",AMBER),
                           ("CLICK", "slow ship",AMBER),
                           ("R","reset", GRAY)]:
        kl = font4.render(key, True, PANEL)
        bw = kl.get_width() + 10
        pygame.draw.rect(win, bc, (lx, y, bw, 17), border_radius=3)
        win.blit(kl, (lx + 5, y + 2))
        win.blit(font3.render(desc, True, WHITE), (lx + bw + 7, y + 3))
        y += 21

    y += 8
    pygame.draw.line(win, (34, 68, 82), (lx, y), (width - 14, y), 1);  y += 8
    for line in ["Ships: ~168 dB source",
                 "TL=20*log10(r)+a*r",
                 "Masked above 118 dB",
                 ""]:
        win.blit(font3.render(line, True, AMBER if "TL=" in line else GRAY), (lx, y));  y += 13

    if msg_timer > 0:
        col = RED if "strand" in msg.lower() else GREEN
        win.blit(font2.render(msg, True, col), (lx, height - 40))


def main():
    running = True
    clock = pygame.time.Clock()

    ships = [Ship(x, slot=i) for i, x in enumerate(SHIP_STARTS)]
    # ships already staggered via slot offset in __init__

    whales = []
    for ly in WHALE_LANES:
        whales.append(Whale(ly))
        whales.append(Whale(ly, start_x=random.randint(60, 180))) #second whale per lane

    score = 0
    safe_count = 0
    strand_count = 0
    message = ""
    msg_timer = 0.0
    sim_time = 0.0

    dragging = None  #ship currently being dragged
    drag_offset_x = 0.0
    mouse_was_down = False

    state = "intro"  # intro -> playing -> end

    while running:
        dt = min(clock.tick(FPS) / 1000.0, 0.05)
        sim_time += dt
        mx, my = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                if state == "intro":
                    state = "playing"
                elif state == "end" or (state == "playing" and event.key == pygame.K_r):
                    main() #restart
                    return
            if state == "playing":
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mouse_was_down = True
                    if mx < OCEAN_W:
                        for s in ships:
                            if not s.finished and s.check_click(mx, my):
                                dragging = s
                                s.being_dragged = True
                                drag_offset_x = s.x - mx
                                break
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    if dragging:
                        dragging.being_dragged = False
                        dragging = None
                    elif mouse_was_down and mx < OCEAN_W:
                        for s in ships:
                            if not s.finished and s.check_click(mx, my):
                                s.toggle_slow()
                                message = f"{'Slowed' if s.is_slow else 'Full speed'} -- {s.noise_db:.0f}dB"
                                msg_timer = 2.5
                                break
                    mouse_was_down = False
                elif event.type == pygame.MOUSEMOTION and dragging:
                    new_x = max(20, min(OCEAN_W - 20, mx + drag_offset_x))
                    dragging.x = new_x
                    dragging.lane = new_x #permanent reroute

        if state == "playing":
            for s in ships:
                s.update()
            for i, s in enumerate(ships):
                if s.finished: #respawn ship at same lane, random slot so speed varies
                    new_s = Ship(s.lane, slot=i, start_y=-40.0)
                    new_s.speed= s.base_speed  #keep same speed
                    new_s.base_speed = s.base_speed
                    ships[i] = new_s

            for w in whales:
                w.move(ships)
                if w.is_stranded and not w.counted_strand:
                    w.counted_strand = True
                    strand_count += 1
                    score = max(0, score - 80)
                    message = "Whale stranded  -80pts"
                    msg_timer = 3.5
                if w.is_safe and not w.counted_safe:
                    w.counted_safe = True
                    safe_count += 1
                    score += 120
                    message = "Whale safe!  +120pts"
                    msg_timer = 2.0

            if msg_timer > 0:
                msg_timer -= dt
            if all(w.is_stranded or w.is_safe for w in whales):
                state = "end"

        # draw ocean
        win.fill(OCEAN)
        win.blit(ocean_bg, (0, 0))

        if state in ("playing", "end"):
            for ly in WHALE_LANES: #draw subtle teal bands showing whale routes
                band = pygame.Surface((OCEAN_W, 58), pygame.SRCALPHA)
                band.fill((*TEAL, 9))
                win.blit(band, (0, ly - 29))
                pygame.draw.line(win, (*TEAL, 34), (0, ly), (OCEAN_W, ly), 1)
                win.blit(font3.render("whale route", True, (*TEAL,)), (5, ly - 10))

            draw_noise_rings(ships, sim_time)

            for s in ships:
                s.draw()
            for w in whales:
                w.draw()

            if dragging: #vertical guide line while dragging
                pygame.draw.line(win, (*AMBER, 80), (int(dragging.x), 0), (int(dragging.x), height), 1)

            hov = next((s for s in ships if not s.finished and s.check_click(mx, my)), None)
            if hov: #hover highlight
                hs = pygame.Surface((OCEAN_W, height), pygame.SRCALPHA)
                pygame.draw.circle(hs, (*AMBER, 55), (int(hov.x), int(hov.y)), 28, 2)
                win.blit(hs, (0, 0))
        else:
            hov = None

        pygame.draw.rect(win, (34, 68, 82), (0, 0, OCEAN_W, height), 2) #ocean border

        draw_panel(whales, score, safe_count, strand_count, message, msg_timer, hov)

        # intro overlay
        if state == "intro":
            ov = pygame.Surface((width, height), pygame.SRCALPHA)
            ov.fill((5, 20, 32, 215))
            win.blit(ov, (0, 0))
            cx = width // 2
            lines = [
                (font1, "SoundScape",  AMBER),
                (font2, "Whale Migration vs Ocean Noise Pollution",WHITE),
                (font3, "",WHITE),
                (font2, "Ships are 168dB underwater.",GRAY),
                (font2, "Above 118dB whales lose navigation.",GRAY),
                (font2, "They wander and strand on beaches.", GRAY),
                (font3, "", WHITE),
                (font2, "DRAG ships off the teal whale lanes.",WHITE),
                (font2, "CLICK a ship to slow it down (quieter).", WHITE),
                (font3, "Green bar = calm.   Yellow = Stressed", YELLOW),
                (font3, "",WHITE),
                (font1, "Press any key to start", AMBER),
            ]
            y = height // 2 - len(lines) * 14
            for f, t, c in lines:
                if t:
                    r = f.render(t, True, c)
                    win.blit(r, (cx - r.get_width() // 2, y))
                y += f.size("A")[1] + 8

        # end screen
        elif state == "end":
            ov = pygame.Surface((width, height), pygame.SRCALPHA)
            ov.fill((4, 14, 24, 210))
            win.blit(ov, (0, 0))
            cx = width // 2
            win_game = strand_count == 0
            hdr = font1.render("ALL WHALES SAFE!" if win_game else "MIGRATION COMPLETE",
                               True, GREEN if win_game else YELLOW)
            win.blit(hdr, (cx - hdr.get_width() // 2, 200))
            y = 265
            for txt, col in [(f"Safe: {safe_count}",GREEN),
                             (f"Stranded: {strand_count}", RED if strand_count else GRAY),
                             (f"Score: {score}",AMBER),
                             ("", None),
                             ("Rerouting ships 20-30mi cuts whale mortality 50%+", GRAY),
                             ("Hatch et al. 2012 -- Marine Pollution Bulletin",    TEAL),
                             ("", None),
                             ("R = try again   ESC = quit",GRAY)]:
                if txt and col:
                    r = font3.render(txt, True, col)
                    win.blit(r, (cx - r.get_width() // 2, y))
                y += 22

        pygame.display.update()

    pygame.quit()


if __name__ == "__main__":
    main()

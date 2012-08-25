#-*- coding: utf-8 -*-

import sys
import cairo as C
import sqlalchemy as sa
import sqlalchemy.sql.functions as func
from datetime import datetime
from mako.template import Template
from os import system
from pyramid.paster import bootstrap
from xonstat.models import *
from xonstat.views.player import player_info_data
from xonstat.util import qfont_decode
from colorsys import rgb_to_hls, hls_to_rgb


# similar to html_colors() from util.py
_contrast_threshold = 0.5

_dec_colors = [ (0.5,0.5,0.5),
                (1.0,0.0,0.0),
                (0.2,1.0,0.0),
                (1.0,1.0,0.0),
                (0.2,0.4,1.0),
                (0.2,1.0,1.0),
                (1.0,0.2,102),
                (1.0,1.0,1.0),
                (0.6,0.6,0.6),
                (0.5,0.5,0.5)
            ]


# maximal number of query results (for testing, set to 0 to get all)
NUM_PLAYERS = 100

# image dimensions (likely breaks layout if changed)
WIDTH   = 560
HEIGHT  = 70

# output filename, parameter is player id
OUTPUT = "output/%d.png"


NICK_POS        = (5,18)
NICK_MAXWIDTH   = 330

GAMES_POS       = (60,35)
GAMES_WIDTH     = 110

WINLOSS_POS     = (505,11)
WINLOSS_WIDTH   = 100

KILLDEATH_POS   = (395,11)
KILLDEATH_WIDTH = 100

PLAYTIME_POS    = (450,64)
PLAYTIME_WIDTH  = 210


# parameters to affect the output, could be changed via URL
params = {
    'bg':           1,                      # 0 - black, 1 - dark_wall, ...
    'overlay':      1,                      # 0 - none, 1 - Archer, ...
    'font':         0,                      # 0 - xolonium, 1 - dejavu sans
}


# parse cmdline parameters (for testing)
for arg in sys.argv[1:]:
    try:
        k,v = arg.split("=")
        if params.has_key(k.lower()):
            params[k] = int(v)
    except:
        continue


def get_data(player):
    """Return player data as dict.
    
    This function is similar to the function in player.py but more optimized
    for this purpose.
    """

    # total games
    # wins/losses
    # kills/deaths
    # duel/dm/tdm/ctf elo + rank
    
    player_id = player.player_id
    
    total_stats = {}
    
    games_played = DBSession.query(
            Game.game_type_cd, func.count(), func.sum(PlayerGameStat.alivetime)).\
            filter(Game.game_id == PlayerGameStat.game_id).\
            filter(PlayerGameStat.player_id == player_id).\
            group_by(Game.game_type_cd).\
            order_by(func.count().desc()).\
            limit(3).all()  # limit to 3 gametypes!
    
    total_stats['games'] = 0
    total_stats['games_breakdown'] = {}  # this is a dictionary inside a dictionary .. dictception?
    total_stats['games_alivetime'] = {}
    total_stats['gametypes'] = []
    for (game_type_cd, games, alivetime) in games_played:
        total_stats['games'] += games
        total_stats['gametypes'].append(game_type_cd)
        total_stats['games_breakdown'][game_type_cd] = games
        total_stats['games_alivetime'][game_type_cd] = alivetime
    
    (total_stats['kills'], total_stats['deaths'], total_stats['alivetime'],) = DBSession.query(
            func.sum(PlayerGameStat.kills),
            func.sum(PlayerGameStat.deaths),
            func.sum(PlayerGameStat.alivetime)).\
            filter(PlayerGameStat.player_id == player_id).\
            one()
    
    (total_stats['wins'],) = DBSession.query(
            func.count("*")).\
            filter(Game.game_id == PlayerGameStat.game_id).\
            filter(PlayerGameStat.player_id == player_id).\
            filter(Game.winner == PlayerGameStat.team or PlayerGameStat.rank == 1).\
            one()
    
    ranks = DBSession.query("game_type_cd", "rank", "max_rank").\
            from_statement(
                "select pr.game_type_cd, pr.rank, overall.max_rank "
                "from player_ranks pr,  "
                   "(select game_type_cd, max(rank) max_rank "
                    "from player_ranks  "
                    "group by game_type_cd) overall "
                "where pr.game_type_cd = overall.game_type_cd  "
                "and player_id = :player_id "
                "order by rank").\
            params(player_id=player_id).all()
    
    ranks_dict = {}
    for gtc,rank,max_rank in ranks:
        ranks_dict[gtc] = (rank, max_rank)

    elos = DBSession.query(PlayerElo).\
            filter_by(player_id=player_id).\
            order_by(PlayerElo.elo.desc()).\
            all()
    
    elos_dict = {}
    for elo in elos:
        if elo.games > 32:
            elos_dict[elo.game_type_cd] = elo.elo
    
    data = {
            'player':player,
            'total_stats':total_stats,
            'ranks':ranks_dict,
            'elos':elos_dict,
        }
        
    #print data
    return data


def render_image(data):
    """Render an image from the given data fields."""
    
    font = "Xolonium"
    if params['font'] == 1:
        font = "DejaVu Sans"

    total_stats = data['total_stats']
    total_games = total_stats['games']
    elos = data["elos"]
    ranks = data["ranks"]


    ## create background

    surf = C.ImageSurface(C.FORMAT_RGB24, WIDTH, HEIGHT)
    ctx = C.Context(surf)
    ctx.set_antialias(C.ANTIALIAS_GRAY)

    # draw background (just plain fillcolor)
    if params['bg'] == 0:
        ctx.rectangle(0, 0, WIDTH, HEIGHT)
        ctx.set_source_rgb(0.04, 0.04, 0.04)  # bgcolor of Xonotic forum
        ctx.fill()
    
    # draw background image (try to get correct tiling, too)
    if params['bg'] > 0:
        bg = None
        if params['bg'] == 1:
            bg = C.ImageSurface.create_from_png("img/dark_wall.png")
        elif params['bg'] == 2:
            bg = C.ImageSurface.create_from_png("img/asfalt.png")
        elif params['bg'] == 3:
            bg = C.ImageSurface.create_from_png("img/broken_noise.png")
        elif params['bg'] == 4:
            bg = C.ImageSurface.create_from_png("img/burried.png")
        elif params['bg'] == 5:
            bg = C.ImageSurface.create_from_png("img/dark_leather.png")
        elif params['bg'] == 6:
            bg = C.ImageSurface.create_from_png("img/txture.png")
        elif params['bg'] == 7:
            bg = C.ImageSurface.create_from_png("img/black_linen_v2.png")
        
        # tile image
        if bg:
            bg_w, bg_h = bg.get_width(), bg.get_height()
            bg_xoff = 0
            while bg_xoff < WIDTH:
                bg_yoff = 0
                while bg_yoff < HEIGHT:
                    ctx.set_source_surface(bg, bg_xoff, bg_yoff)
                    ctx.paint()
                    bg_yoff += bg_h
                bg_xoff += bg_w
    
    # draw overlay graphic
    if params['overlay'] > 0:
        overlay = None
        if params['overlay'] == 1:
            overlay = C.ImageSurface.create_from_png("img/overlay.png")
        if overlay:
            ctx.set_source_surface(overlay, 0, 0)
            ctx.mask_surface(overlay)
            ctx.paint()


    ## draw player's nickname with fancy colors
    
    # deocde nick, strip all weird-looking characters
    qstr = qfont_decode(player.nick).replace('^^', '^').replace(u'\x00', ' ')
    chars = []
    for c in qstr:
        if ord(c) < 128:
            chars.append(c)
    qstr = ''.join(chars)
    stripped_nick = strip_colors(qstr)
    
    # fontsize is reduced if width gets too large
    ctx.select_font_face(font, C.FONT_SLANT_NORMAL, C.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(20)
    xoff, yoff, tw, th = ctx.text_extents(stripped_nick)[:4]
    if tw > NICK_MAXWIDTH:
        ctx.set_font_size(18)
        xoff, yoff, tw, th = ctx.text_extents(stripped_nick)[:4]
        if tw > NICK_MAXWIDTH:
            ctx.set_font_size(16)
            xoff, yoff, tw, th = ctx.text_extents(stripped_nick)[:4]
            if tw > NICK_MAXWIDTH:
                ctx.set_font_size(14)
                xoff, yoff, tw, th = ctx.text_extents(stripped_nick)[:4]
                if tw > NICK_MAXWIDTH:
                    ctx.set_font_size(12)
    
    
    # split up nick into colored segments and draw each of them
    
    # split nick into colored segments
    parts = []
    pos = 1
    while True:
        npos = qstr.find('^', pos)
        if npos < 0:
            parts.append(qstr[pos-1:])
            break;
        parts.append(qstr[pos-1:npos])
        pos = npos+1
    
    xoffset = 0
    for txt in parts:
        r,g,b = _dec_colors[7]
        try:
            if txt.startswith('^'):
                txt = txt[1:]
                if txt.startswith('x'):
                    r = int(txt[1] * 2, 16) / 255.0
                    g = int(txt[2] * 2, 16) / 255.0
                    b = int(txt[3] * 2, 16) / 255.0
                    hue, light, satur = rgb_to_hls(r, g, b)
                    if light < _contrast_threshold:
                        light = _contrast_threshold
                        r, g, b = hls_to_rgb(hue, light, satur)
                    txt = txt[4:]
                else:
                    r,g,b = _dec_colors[int(txt[0])]
                    txt = txt[1:]
        except:
            r,g,b = _dec_colors[7]
        
        if len(txt) < 1:
            # only colorcode and no real text, skip this
            continue
        
        ctx.set_source_rgb(r, g, b)
        ctx.move_to(NICK_POS[0] + xoffset, NICK_POS[1])
        ctx.show_text(txt)

        xoff, yoff, tw, th = ctx.text_extents(txt)[:4]
        xoffset += tw + 2


    ## print elos and ranks
    
    # show up to three gametypes the player has participated in
    xoffset = 0
    for gt in total_stats['gametypes'][:3]:
        ctx.select_font_face(font, C.FONT_SLANT_NORMAL, C.FONT_WEIGHT_BOLD)
        ctx.set_font_size(10)
        ctx.set_source_rgb(1.0, 1.0, 1.0)
        txt = "[ %s ]" % gt.upper()
        xoff, yoff, tw, th = ctx.text_extents(txt)[:4]
        ctx.move_to(GAMES_POS[0]+xoffset-xoff-tw/2, GAMES_POS[1]-yoff-4)
        ctx.show_text(txt)
        
        old_aa = ctx.get_antialias()
        ctx.set_antialias(C.ANTIALIAS_NONE)
        ctx.set_source_rgb(0.8, 0.8, 0.8)
        ctx.set_line_width(1)
        ctx.move_to(GAMES_POS[0]+xoffset-GAMES_WIDTH/2+5, GAMES_POS[1]+8)
        ctx.line_to(GAMES_POS[0]+xoffset+GAMES_WIDTH/2-5, GAMES_POS[1]+8)
        ctx.stroke()
        ctx.move_to(GAMES_POS[0]+xoffset-GAMES_WIDTH/2+5, GAMES_POS[1]+32)
        ctx.line_to(GAMES_POS[0]+xoffset+GAMES_WIDTH/2-5, GAMES_POS[1]+32)
        ctx.stroke()
        ctx.set_antialias(old_aa)
        
        if not elos.has_key(gt) or not ranks.has_key(gt):
            ctx.select_font_face(font, C.FONT_SLANT_NORMAL, C.FONT_WEIGHT_BOLD)
            ctx.set_font_size(12)
            ctx.set_source_rgb(0.8, 0.2, 0.2)
            txt = "no stats yet!"
            xoff, yoff, tw, th = ctx.text_extents(txt)[:4]
            ctx.move_to(GAMES_POS[0]+xoffset-xoff-tw/2, GAMES_POS[1]+28-yoff-4)
            ctx.save()
            ctx.rotate(math.radians(-10))
            ctx.show_text(txt)
            ctx.restore()
        else:
            ctx.select_font_face(font, C.FONT_SLANT_NORMAL, C.FONT_WEIGHT_NORMAL)
            ctx.set_font_size(10)
            ctx.set_source_rgb(1.0, 1.0, 0.5)
            txt = "Elo: %.0f" % round(elos[gt], 0)
            xoff, yoff, tw, th = ctx.text_extents(txt)[:4]
            ctx.move_to(GAMES_POS[0]+xoffset-xoff-tw/2, GAMES_POS[1]+15-yoff-4)
            ctx.show_text(txt)
            
            ctx.select_font_face(font, C.FONT_SLANT_NORMAL, C.FONT_WEIGHT_NORMAL)
            ctx.set_font_size(8)
            ctx.set_source_rgb(0.8, 0.8, 0.8)
            txt = "Rank %d of %d" % ranks[gt]
            xoff, yoff, tw, th = ctx.text_extents(txt)[:4]
            ctx.move_to(GAMES_POS[0]+xoffset-xoff-tw/2, GAMES_POS[1]+25-yoff-3)
            ctx.show_text(txt)
        
        xoffset += GAMES_WIDTH


    # print win percentage
    
    ctx.rectangle(WINLOSS_POS[0]-WINLOSS_WIDTH/2, WINLOSS_POS[1]-7, WINLOSS_WIDTH, 14)
    ctx.set_source_rgba(0.8, 0.8, 0.8, 0.1)
    ctx.fill();
    
    ctx.select_font_face(font, C.FONT_SLANT_NORMAL, C.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(10)
    ctx.set_source_rgb(0.8, 0.8, 0.8)
    txt = "Win Percentage"
    xoff, yoff, tw, th = ctx.text_extents(txt)[:4]
    ctx.move_to(WINLOSS_POS[0]-xoff-tw/2, WINLOSS_POS[1]-yoff-3)
    ctx.show_text(txt)
    
    txt = "???"
    if total_games > 0 and total_stats['wins'] is not None:
        ratio = float(total_stats['wins'])/total_games
        txt = "%.2f%%" % round(ratio * 100, 2)
    ctx.select_font_face(font, C.FONT_SLANT_NORMAL, C.FONT_WEIGHT_BOLD)
    ctx.set_font_size(12)
    if ratio >= 0.90:
        ctx.set_source_rgb(0.2, 1.0, 1.0)
    elif ratio >= 0.75:
        ctx.set_source_rgb(0.5, 1.0, 1.0)
    elif ratio >= 0.5:
        ctx.set_source_rgb(0.5, 1.0, 0.8)
    elif ratio >= 0.25:
        ctx.set_source_rgb(0.8, 1.0, 0.5)
    else:
        ctx.set_source_rgb(1.0, 1.0, 0.5)
    xoff, yoff, tw, th = ctx.text_extents(txt)[:4]
    ctx.move_to(WINLOSS_POS[0]-xoff-tw/2, WINLOSS_POS[1]+16-yoff-4)
    ctx.show_text(txt)
    
    ctx.select_font_face(font, C.FONT_SLANT_NORMAL, C.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(8)
    ctx.set_source_rgb(0.6, 0.8, 0.6)
    txt = "%d wins" % total_stats["wins"]
    xoff, yoff, tw, th = ctx.text_extents(txt)[:4]
    ctx.move_to(WINLOSS_POS[0]-xoff-tw/2, WINLOSS_POS[1]+28-yoff-3)
    ctx.show_text(txt)
    ctx.set_source_rgb(0.8, 0.6, 0.6)
    txt = "%d losses" % (total_games-total_stats['wins'])
    xoff, yoff, tw, th = ctx.text_extents(txt)[:4]
    ctx.move_to(WINLOSS_POS[0]-xoff-tw/2, WINLOSS_POS[1]+38-yoff-3)
    ctx.show_text(txt)


    # print kill/death ratio
    
    ctx.rectangle(KILLDEATH_POS[0]-KILLDEATH_WIDTH/2, KILLDEATH_POS[1]-7, KILLDEATH_WIDTH, 14)
    ctx.set_source_rgba(0.8, 0.8, 0.8, 0.1)
    ctx.fill()
    
    ctx.select_font_face(font, C.FONT_SLANT_NORMAL, C.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(10)
    ctx.set_source_rgb(0.8, 0.8, 0.8)
    txt = "Kill Ratio"
    xoff, yoff, tw, th = ctx.text_extents(txt)[:4]
    ctx.move_to(KILLDEATH_POS[0]-xoff-tw/2, KILLDEATH_POS[1]-yoff-3)
    ctx.show_text(txt)
    
    txt = "???"
    if total_stats['deaths'] > 0 and total_stats['kills'] is not None:
        ratio = float(total_stats['kills'])/total_stats['deaths']
        txt = "%.3f" % round(ratio, 3)
    ctx.select_font_face(font, C.FONT_SLANT_NORMAL, C.FONT_WEIGHT_BOLD)
    ctx.set_font_size(12)
    if ratio >= 3:
        ctx.set_source_rgb(0.0, 1.0, 0.0)
    elif ratio >= 2:
        ctx.set_source_rgb(0.2, 1.0, 0.2)
    elif ratio >= 1:
        ctx.set_source_rgb(0.5, 1.0, 0.5)
    elif ratio >= 0.5:
        ctx.set_source_rgb(1.0, 0.5, 0.5)
    else:
        ctx.set_source_rgb(1.0, 0.2, 0.2)
    xoff, yoff, tw, th = ctx.text_extents(txt)[:4]
    ctx.move_to(KILLDEATH_POS[0]-xoff-tw/2, KILLDEATH_POS[1]+16-yoff-4)
    ctx.show_text(txt)

    ctx.select_font_face(font, C.FONT_SLANT_NORMAL, C.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(8)
    ctx.set_source_rgb(0.6, 0.8, 0.6)
    txt = "%d kills" % total_stats["kills"]
    xoff, yoff, tw, th = ctx.text_extents(txt)[:4]
    ctx.move_to(KILLDEATH_POS[0]-xoff-tw/2, KILLDEATH_POS[1]+28-yoff-3)
    ctx.show_text(txt)
    ctx.set_source_rgb(0.8, 0.6, 0.6)
    txt = "%d deaths" % total_stats['deaths']
    xoff, yoff, tw, th = ctx.text_extents(txt)[:4]
    ctx.move_to(KILLDEATH_POS[0]-xoff-tw/2, KILLDEATH_POS[1]+38-yoff-3)
    ctx.show_text(txt)


    # print playing time
    
    ctx.rectangle( PLAYTIME_POS[0]-PLAYTIME_WIDTH/2, PLAYTIME_POS[1]-7, PLAYTIME_WIDTH, 14)
    ctx.set_source_rgba(0.8, 0.8, 0.8, 0.6)
    ctx.fill();
    
    ctx.select_font_face(font, C.FONT_SLANT_NORMAL, C.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(10)
    ctx.set_source_rgb(0.1, 0.1, 0.1)
    txt = "Playing time: %s" % str(total_stats['alivetime'])
    xoff, yoff, tw, th = ctx.text_extents(txt)[:4]
    ctx.move_to(PLAYTIME_POS[0]-xoff-tw/2, PLAYTIME_POS[1]-yoff-4)
    ctx.show_text(txt)


    # save to PNG
    surf.write_to_png(OUTPUT % data['player'].player_id)


# environment setup
env = bootstrap('../../../development.ini')
req = env['request']
req.matchdict = {'id':3}

print "Requesting player data from db ..."
start = datetime.now()
players = DBSession.query(Player).\
        filter(Player.player_id == PlayerElo.player_id).\
        filter(Player.nick != None).\
        filter(Player.player_id > 2).\
        filter(Player.active_ind == True).\
        limit(NUM_PLAYERS).all()
stop = datetime.now()
print "Query took %.2f seconds" % (stop-start).total_seconds()

print "Creating badges for %d active players ..." % len(players)
start = datetime.now()
data_time, render_time = 0,0
for player in players:
    req.matchdict['id'] = player.player_id
    
    sstart = datetime.now()
    #data = player_info_data(req)
    data = get_data(player)
    sstop = datetime.now()
    data_time += (sstop-sstart).total_seconds()
    
    print "\r  #%-5d" % player.player_id,
    sys.stdout.flush()

    sstart = datetime.now()
    render_image(data)
    sstop = datetime.now()
    render_time += (sstop-sstart).total_seconds()
print

stop = datetime.now()
print "Creating the badges took %.2f seconds (%.2f s per player)" % ((stop-start).total_seconds(), (stop-start).total_seconds()/float(len(players)))
print " Total time for getting data: %.2f s" % data_time
print " Total time for renering images: %.2f s" % render_time

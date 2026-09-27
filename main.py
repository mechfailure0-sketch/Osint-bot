import os
import io
import socket
import asyncio
import subprocess
import tempfile
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

TOKEN = os.environ["TOKEN"]

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

TIMEOUT = 15
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

USERNAME_SITES = {
    "GitHub":       ("https://github.com/{}", ["Not Found"]),
    "Twitter/X":    ("https://x.com/{}", None),
    "Instagram":    ("https://instagram.com/{}", ["Sorry, this page isn't available", "Page Not Found"]),
    "Reddit":       ("https://reddit.com/user/{}", ["page not found", "Sorry, nobody on Reddit"]),
    "TikTok":       ("https://tiktok.com/@{}", ["Couldn't find this account", "Couldn't find this user"]),
    "Twitch":       ("https://twitch.tv/{}", None),
    "YouTube":      ("https://youtube.com/@{}", ["This page isn't available"]),
    "Steam":        ("https://steamcommunity.com/id/{}", ["The specified profile could not be found"]),
    "Pinterest":    ("https://pinterest.com/{}", ["Sorry! We couldn't find that page"]),
    "Telegram":     ("https://t.me/{}", ["tgme_page_icon", "If you have Telegram"]),
    "Snapchat":     ("https://snapchat.com/add/{}", ["This content could not be found"]),
    "Roblox":       ("https://roblox.com/user.aspx?username={}", ["Page cannot be found"]),
    "Spotify":      ("https://open.spotify.com/user/{}", ["Page not found"]),
    "Medium":       ("https://medium.com/@{}", ["404"]),
    "DeviantArt":   ("https://deviantart.com/{}", ["Page Not Found"]),
    "Patreon":      ("https://patreon.com/{}", ["Page not found"]),
    "SoundCloud":   ("https://soundcloud.com/{}", ["We can't find that user"]),
    "Behance":      ("https://behance.net/{}", ["Page not found"]),
    "Dribbble":     ("https://dribbble.com/{}", ["Page not found"]),
    "GitLab":       ("https://gitlab.com/{}", ["404"]),
    "BitBucket":    ("https://bitbucket.org/{}", ["404"]),
    "Keybase":      ("https://keybase.io/{}", None),
    "Mastodon":     ("https://mastodon.social/@{}", ["Page not found"]),
    "VK":           ("https://vk.com/{}", None),
    "Flickr":       ("https://flickr.com/people/{}", ["Page not found"]),
    "Tumblr":       ("https://{}.tumblr.com", None),
    "Wattpad":      ("https://wattpad.com/user/{}", ["Page not found"]),
    "Vimeo":        ("https://vimeo.com/{}", ["Page not found"]),
    "Chess.com":    ("https://chess.com/member/{}", ["Page not found"]),
}

async def check_username_site(session, username, site_data):
    url, signatures = site_data
    target = url.format(username)
    try:
        async with session.get(target, timeout=aiohttp.ClientTimeout(total=TIMEOUT), allow_redirects=True) as r:
            if r.status != 200:
                return False
            if signatures is None:
                return True
            text = await r.text(errors="ignore")
            text_lower = text.lower()
            for sig in signatures:
                if sig.lower() in text_lower:
                    return False
            return True
    except Exception:
        return False

async def scan_username(username):
    found = []
    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as session:
        tasks = [check_username_site(session, username, data) for data in USERNAME_SITES.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for (name, _), ok in zip(USERNAME_SITES.items(), results):
            if ok is True:
                found.append(name)
    return found

def extract_exif(image_bytes):
    out = {}
    try:
        img = Image.open(io.BytesIO(image_bytes))
        out["format"] = img.format
        out["size"] = f"{img.width}x{img.height}"
        exif = img.getexif()
        if not exif:
            return out
        for tag_id, value in exif.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag == "GPSInfo":
                gps = {}
                for k, v in value.items():
                    gps[GPSTAGS.get(k, k)] = v
                out["GPS"] = gps
            else:
                if isinstance(value, bytes):
                    continue
                out[str(tag)] = str(value)[:200]
    except Exception as e:
        out["error"] = str(e)
    return out

def gps_to_decimal(gps_info):
    try:
        def to_deg(v):
            d, m, s = v
            return float(d) + float(m) / 60 + float(s) / 3600
        lat = to_deg(gps_info["GPSLatitude"])
        lon = to_deg(gps_info["GPSLongitude"])
        if gps_info.get("GPSLatitudeRef") == "S":
            lat = -lat
        if gps_info.get("GPSLongitudeRef") == "W":
            lon = -lon
        return lat, lon
    except Exception:
        return None

async def trace_url(url):
    chain = [url]
    try:
        async with aiohttp.ClientSession(headers={"User-Agent": UA}) as session:
            current = url
            for _ in range(10):
                async with session.get(current, timeout=aiohttp.ClientTimeout(total=TIMEOUT), allow_redirects=False) as r:
                    if r.status in (301, 302, 303, 307, 308):
                        loc = r.headers.get("Location")
                        if not loc:
                            break
                        if loc.startswith("/"):
                            p = urlparse(current)
                            loc = f"{p.scheme}://{p.netloc}{loc}"
                        chain.append(loc)
                        current = loc
                    else:
                        break
    except Exception as e:
        chain.append(f"erreur: {e}")
    return chain

@tree.command(name="username", description="scanne un pseudo sur ~30 sites publics")
@app_commands.describe(pseudo="le pseudo a chercher")
async def username(interaction: discord.Interaction, pseudo: str):
    await interaction.response.defer()
    found = await scan_username(pseudo)
    embed = discord.Embed(title=f"OSINT — {pseudo}", color=0x00b0ff if found else 0xff3b30)
    if found:
        embed.add_field(name=f"Trouve sur {len(found)} site(s)", value="\n".join(f"• {s}" for s in found), inline=False)
    else:
        embed.description = "aucun resultat public"
    embed.set_footer(text="detection par contenu — sources publiques")
    await interaction.followup.send(embed=embed)

@tree.command(name="sherlock", description="scan etendu — 400+ sites via Sherlock")
@app_commands.describe(pseudo="le pseudo a chercher")
async def sherlock_cmd(interaction: discord.Interaction, pseudo: str):
    await interaction.response.defer()
    outfile = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            outfile = f.name
        proc = await asyncio.create_subprocess_exec(
            "sherlock", pseudo, "--print-found", "--timeout", "20",
            "--output", outfile,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await asyncio.wait_for(proc.communicate(), timeout=300)
        with open(outfile, "r", errors="ignore") as f:
            content = f.read()
        lines = [l.strip() for l in content.splitlines() if l.strip().startswith("http")]
        embed = discord.Embed(title=f"Sherlock — {pseudo}", color=0x00b0ff if lines else 0xff3b30)
        if lines:
            embed.add_field(name=f"Trouve sur {len(lines)} site(s)", value="\n".join(f"• {l}" for l in lines[:25]), inline=False)
            if len(lines) > 25:
                embed.set_footer(text=f"+{len(lines)-25} autres resultats")
            else:
                embed.set_footer(text="scan sherlock-project — timeout 20s/site")
        else:
            embed.description = "aucun resultat public"
        await interaction.followup.send(embed=embed)
    except asyncio.TimeoutError:
        await interaction.followup.send("timeout — le scan a depasse 5 minutes")
    except Exception as e:
        await interaction.followup.send(f"erreur : {str(e)[:200]}")

@tree.command(name="holehe", description="check si un email est enregistre sur 120+ sites")
@app_commands.describe(email="l'adresse email a verifier")
async def holehe_cmd(interaction: discord.Interaction, email: str):
    await interaction.response.defer()
    if "@" not in email:
        await interaction.followup.send("email invalide")
        return
    try:
        proc = await asyncio.create_subprocess_exec(
            "holehe", email, "--only-used",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=150)
        output = stdout.decode(errors="ignore")
        sites = [l.strip() for l in output.splitlines() if l.strip().startswith("[+]")]
        embed = discord.Embed(title=f"Holehe — {email}", color=0x00b0ff if sites else 0xff3b30)
        if sites:
            cleaned = [s.replace("[+]", "•").strip() for s in sites]
            embed.add_field(name=f"Enregistre sur {len(sites)} site(s)", value="\n".join(cleaned[:25]), inline=False)
            if len(sites) > 25:
                embed.set_footer(text=f"+{len(sites)-25} autres — la cible n'est pas notifiee")
            else:
                embed.set_footer(text="detection via recovery — cible non notifiee")
        else:
            embed.description = "aucun compte detecte"
        await interaction.followup.send(embed=embed)
    except asyncio.TimeoutError:
        await interaction.followup.send("timeout — le scan a depasse 2min30")
    except Exception as e:
        await interaction.followup.send(f"erreur : {str(e)[:200]}")

@tree.command(name="email", description="check une adresse email dans les fuites publiques")
@app_commands.describe(email="l'email a verifier")
async def email(interaction: discord.Interaction, email: str):
    embed = discord.Embed(title="OSINT — email", color=0x00b0ff)
    embed.add_field(name="cible", value=f"`{email}`", inline=False)
    embed.add_field(name="HaveIBeenPwned", value=f"https://haveibeenpwned.com/account/{email}", inline=False)
    embed.add_field(name="Firefox Monitor", value=f"https://monitor.mozilla.org/?email={email}", inline=False)
    embed.add_field(name="DeHashed", value=f"https://dehashed.com/search?query={email}", inline=False)
    embed.set_footer(text="verifie manuellement les liens")
    await interaction.response.send_message(embed=embed)

@tree.command(name="domain", description="DNS + WHOIS + crt.sh + archive")
@app_commands.describe(domain="le domaine (ex: example.com)")
async def domain(interaction: discord.Interaction, domain: str):
    await interaction.response.defer()
    try:
        ip = socket.gethostbyname(domain)
    except Exception:
        ip = "echec"
    embed = discord.Embed(title=f"OSINT — {domain}", color=0x00b0ff)
    embed.add_field(name="IP resolue", value=ip, inline=False)
    embed.add_field(name="WHOIS", value=f"https://who.is/whois/{domain}", inline=False)
    embed.add_field(name="crt.sh", value=f"https://crt.sh/?q={domain}", inline=False)
    embed.add_field(name="Wayback", value=f"https://web.archive.org/web/*/{domain}", inline=False)
    embed.add_field(name="VirusTotal", value=f"https://virustotal.com/gui/domain/{domain}", inline=False)
    embed.add_field(name="urlscan.io", value=f"https://urlscan.io/domain/{domain}", inline=False)
    embed.set_footer(text="sources publiques")
    await interaction.followup.send(embed=embed)

@tree.command(name="dns", description="resolution DNS complete")
@app_commands.describe(domain="le domaine a interroger")
async def dns(interaction: discord.Interaction, domain: str):
    await interaction.response.defer()
    try:
        loop = asyncio.get_event_loop()
        a_records = await loop.run_in_executor(None, lambda: socket.gethostbyname_ex(domain)[2])
    except Exception:
        a_records = ["echec"]
    embed = discord.Embed(title=f"DNS — {domain}", color=0x00b0ff)
    embed.add_field(name="A (IPv4)", value="\n".join(a_records), inline=False)
    embed.add_field(name="MX / NS / TXT", value=f"https://dns.google/query?name={domain}&type=MX\nhttps://dns.google/query?name={domain}&type=NS\nhttps://dns.google/query?name={domain}&type=TXT", inline=False)
    embed.set_footer(text="socket + dns.google")
    await interaction.followup.send(embed=embed)

@tree.command(name="whois", description="whois complet d'un domaine")
@app_commands.describe(domain="le domaine")
async def whois(interaction: discord.Interaction, domain: str):
    embed = discord.Embed(title=f"WHOIS — {domain}", color=0x00b0ff)
    embed.add_field(name="who.is", value=f"https://who.is/whois/{domain}", inline=False)
    embed.add_field(name="ICANN", value=f"https://lookup.icann.org/en/lookup?name={domain}", inline=False)
    embed.add_field(name="DomainTools", value=f"https://whois.domaintools.com/{domain}", inline=False)
    embed.set_footer(text="sources publiques")
    await interaction.response.send_message(embed=embed)

@tree.command(name="ip", description="infos sur une IP")
@app_commands.describe(ip="l'adresse IP")
async def ip_lookup(interaction: discord.Interaction, ip: str):
    embed = discord.Embed(title=f"OSINT — {ip}", color=0x00b0ff)
    embed.add_field(name="ipinfo.io", value=f"https://ipinfo.io/{ip}", inline=False)
    embed.add_field(name="Shodan", value=f"https://shodan.io/host/{ip}", inline=False)
    embed.add_field(name="AbuseIPDB", value=f"https://abuseipdb.com/check/{ip}", inline=False)
    embed.add_field(name="VirusTotal", value=f"https://virustotal.com/gui/ip-address/{ip}", inline=False)
    embed.set_footer(text="sources publiques")
    await interaction.response.send_message(embed=embed)

@tree.command(name="image", description="extrait les metadonnees EXIF d'une image")
@app_commands.describe(fichier="l'image a analyser (PNG/JPG)")
async def image_cmd(interaction: discord.Interaction, fichier: discord.Attachment):
    await interaction.response.defer()
    try:
        data = await fichier.read()
        exif = extract_exif(data)
    except Exception as e:
        await interaction.followup.send(f"erreur lecture : {e}")
        return
    embed = discord.Embed(title="EXIF — image", color=0x00b0ff)
    if "format" in exif:
        embed.add_field(name="format", value=f"{exif.get('format')} — {exif.get('size')}", inline=False)
    if "GPS" in exif:
        coords = gps_to_decimal(exif["GPS"])
        if coords:
            lat, lon = coords
            embed.add_field(name="GPS", value=f"{lat:.6f}, {lon:.6f}\n[Google Maps](https://maps.google.com/?q={lat},{lon})", inline=False)
        else:
            embed.add_field(name="GPS (brut)", value=str(exif["GPS"])[:1000], inline=False)
    interesting = ["Make", "Model", "DateTime", "Software", "LensModel", "Artist", "Copyright"]
    for k in interesting:
        if k in exif:
            embed.add_field(name=k, value=exif[k][:200], inline=False)
    if len(embed.fields) == 0:
        embed.description = "aucune metadonnee EXIF (image nettoyee ou format non supporte)"
    embed.set_footer(text=f"analyse de {fichier.filename}")
    await interaction.followup.send(embed=embed)

@tree.command(name="reverse", description="reverse image search")
@app_commands.describe(fichier="l'image a chercher")
async def reverse(interaction: discord.Interaction, fichier: discord.Attachment):
    embed = discord.Embed(title="Reverse image search", color=0x00b0ff)
    embed.add_field(name="moteurs", value="Upload l'image sur un des sites :\n• [Google Images](https://images.google.com/)\n• [Yandex Images](https://yandex.com/images/)\n• [TinEye](https://tineye.com/)\n• [Bing Visual](https://www.bing.com/visualsearch)", inline=False)
    embed.set_footer(text="upload manuel requis")
    await interaction.response.send_message(embed=embed)

@tree.command(name="trace", description="deballe une URL raccourcie")
@app_commands.describe(url="l'URL a tracer")
async def trace(interaction: discord.Interaction, url: str):
    await interaction.response.defer()
    if not url.startswith("http"):
        url = "http://" + url
    chain = await trace_url(url)
    embed = discord.Embed(title="URL trace", color=0x00b0ff)
    embed.add_field(name=f"{len(chain)} etape(s)", value="\n".join(f"{i+1}. {u[:150]}" for i, u in enumerate(chain)), inline=False)
    embed.set_footer(text="chaine de redirections")
    await interaction.followup.send(embed=embed)

@tree.command(name="phone", description="lookup numero de telephone")
@app_commands.describe(numero="le numero (format international ex: +33612345678)")
async def phone(interaction: discord.Interaction, numero: str):
    clean = "".join(c for c in numero if c.isdigit() or c == "+")
    embed = discord.Embed(title=f"OSINT — {numero}", color=0x00b0ff)
    embed.add_field(name="Truecaller", value=f"https://truecaller.com/search/{clean}", inline=False)
    embed.add_field(name="NumLookup", value=f"https://numlookup.com/phone-lookup?phone={clean}", inline=False)
    embed.add_field(name="Free Carrier Lookup", value="https://freecarrierlookup.com/", inline=False)
    embed.set_footer(text="sources publiques — verif manuelle")
    await interaction.response.send_message(embed=embed)

@tree.command(name="steam", description="lookup un profil Steam")
@app_commands.describe(pseudo="le pseudo Steam ou SteamID")
async def steam(interaction: discord.Interaction, pseudo: str):
    embed = discord.Embed(title=f"Steam — {pseudo}", color=0x00b0ff)
    embed.add_field(name="profil", value=f"https://steamcommunity.com/id/{pseudo}", inline=False)
    embed.add_field(name="SteamID lookup", value=f"https://steamid.io/lookup/{pseudo}", inline=False)
    embed.add_field(name="SteamDB", value=f"https://steamdb.info/search/?a=user&q={pseudo}", inline=False)
    embed.set_footer(text="sources publiques")
    await interaction.response.send_message(embed=embed)

@tree.command(name="help", description="liste des commandes OSINT")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="Bot OSINT — commandes", color=0x00b0ff)
    embed.add_field(name="/username", value="scanne un pseudo sur ~30 sites", inline=False)
    embed.add_field(name="/sherlock", value="scan etendu 400+ sites", inline=False)
    embed.add_field(name="/holehe", value="email sur 120+ sites (cible non notifiee)", inline=False)
    embed.add_field(name="/email", value="check email dans HIBP + Firefox Monitor", inline=False)
    embed.add_field(name="/domain", value="DNS + WHOIS + crt.sh + archive + VT", inline=False)
    embed.add_field(name="/dns", value="resolution DNS A/MX/NS/TXT", inline=False)
    embed.add_field(name="/whois", value="whois complet d'un domaine", inline=False)
    embed.add_field(name="/ip", value="ipinfo + Shodan + AbuseIPDB + VT", inline=False)
    embed.add_field(name="/image", value="extrait EXIF (GPS, appareil, date)", inline=False)
    embed.add_field(name="/reverse", value="reverse image search", inline=False)
    embed.add_field(name="/trace", value="deballe URL raccourcie", inline=False)
    embed.add_field(name="/phone", value="lookup numero", inline=False)
    embed.add_field(name="/steam", value="lookup profil Steam", inline=False)
    embed.set_footer(text="sources ouvertes uniquement")
    await interaction.response.send_message(embed=embed)

@bot.event
async def on_ready():
    await tree.sync()
    print(f"connecte : {bot.user}")

bot.run(TOKEN)

# language: Python, file: main.py
# target: Python 3.11+, discord.py 2.x
# *sources publiques uniquement — pas d'accès privé*

import os
import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import asyncio
import socket

TOKEN = os.environ["TOKEN"]

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

TIMEOUT = 15

USERNAME_SITES = {
    "GitHub":       "https://github.com/{}",
    "Twitter/X":    "https://x.com/{}",
    "Instagram":    "https://instagram.com/{}",
    "Reddit":       "https://reddit.com/user/{}",
    "TikTok":       "https://tiktok.com/@{}",
    "Twitch":       "https://twitch.tv/{}",
    "YouTube":      "https://youtube.com/@{}",
    "Steam":        "https://steamcommunity.com/id/{}",
    "Pinterest":    "https://pinterest.com/{}",
    "Telegram":     "https://t.me/{}",
    "Snapchat":     "https://snapchat.com/add/{}",
    "Roblox":       "https://roblox.com/user.aspx?username={}",
    "Spotify":      "https://open.spotify.com/user/{}",
    "Medium":       "https://medium.com/@{}",
    "DeviantArt":   "https://deviantart.com/{}",
    "Patreon":      "https://patreon.com/{}",
    "SoundCloud":   "https://soundcloud.com/{}",
    "Behance":      "https://behance.net/{}",
    "Dribbble":     "https://dribbble.com/{}",
    "GitLab":       "https://gitlab.com/{}",
    "BitBucket":    "https://bitbucket.org/{}",
    "Keybase":      "https://keybase.io/{}",
    "Mastodon":     "https://mastodon.social/@{}",
    "VK":           "https://vk.com/{}",
    "Flickr":       "https://flickr.com/people/{}",
}

async def check_url(session, url):
    try:
        async with session.head(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT),
                                 allow_redirects=True) as r:
            return r.status == 200
    except Exception:
        return False

async def scan_username(username):
    found = []
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
        tasks = {name: check_url(session, url.format(username))
                 for name, url in USERNAME_SITES.items()}
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for (name, _), res in zip(tasks.items(), results):
            if res is True:
                found.append(name)
    return found

async def dns_lookup(domain):
    try:
        return socket.gethostbyname(domain)
    except Exception:
        return None

@tree.command(name="username", description="scanne un pseudo sur les sites publics")
@app_commands.describe(pseudo="le pseudo à chercher")
async def username(interaction: discord.Interaction, pseudo: str):
    await interaction.response.defer()
    found = await scan_username(pseudo)
    embed = discord.Embed(
        title=f"OSINT — {pseudo}",
        color=0x00b0ff if found else 0xff3b30
    )
    if found:
        embed.add_field(
            name=f"Trouvé sur {len(found)} site(s)",
            value="\n".join(f"• {s}" for s in found),
            inline=False
        )
    else:
        embed.description = "aucun résultat public"
    embed.set_footer(text="sources publiques uniquement")
    await interaction.followup.send(embed=embed)

@tree.command(name="email", description="check une adresse email dans les fuites publiques")
@app_commands.describe(email="l'email à vérifier")
async def email(interaction: discord.Interaction, email: str):
    embed = discord.Embed(title="OSINT — email", color=0x00b0ff)
    embed.add_field(name="cible", value=f"`{email}`", inline=False)
    embed.add_field(name="HaveIBeenPwned",
                    value=f"https://haveibeenpwned.com/account/{email}",
                    inline=False)
    embed.set_footer(text="vérifie manuellement le lien")
    await interaction.response.send_message(embed=embed)

@tree.command(name="domain", description="résolution DNS + infos sur un domaine")
@app_commands.describe(domain="le domaine (ex: example.com)")
async def domain(interaction: discord.Interaction, domain: str):
    await interaction.response.defer()
    ip = await dns_lookup(domain)
    embed = discord.Embed(title=f"OSINT — {domain}", color=0x00b0ff)
    embed.add_field(name="IP résolue", value=ip or "échec", inline=False)
    embed.add_field(name="WHOIS", value=f"https://who.is/whois/{domain}", inline=False)
    embed.add_field(name="crt.sh", value=f"https://crt.sh/?q={domain}", inline=False)
    embed.add_field(name="Wayback",
                    value=f"https://web.archive.org/web/*/{domain}",
                    inline=False)
    embed.set_footer(text="sources publiques uniquement")
    await interaction.followup.send(embed=embed)

@tree.command(name="ip", description="infos basiques sur une IP")
@app_commands.describe(ip="l'adresse IP")
async def ip_lookup(interaction: discord.Interaction, ip: str):
    embed = discord.Embed(title=f"OSINT — {ip}", color=0x00b0ff)
    embed.add_field(name="ipinfo.io", value=f"https://ipinfo.io/{ip}", inline=False)
    embed.add_field(name="Shodan", value=f"https://shodan.io/host/{ip}", inline=False)
    embed.set_footer(text="sources publiques uniquement")
    await interaction.response.send_message(embed=embed)

@tree.command(name="help", description="liste des commandes OSINT")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="Bot OSINT — commandes", color=0x00b0ff)
    embed.add_field(name="/username", value="scanne un pseudo sur 25 sites", inline=False)
    embed.add_field(name="/email", value="check email dans HIBP", inline=False)
    embed.add_field(name="/domain", value="DNS + WHOIS + crt.sh + archive", inline=False)
    embed.add_field(name="/ip", value="ipinfo + shodan", inline=False)
    embed.set_footer(text="sources ouvertes uniquement")
    await interaction.response.send_message(embed=embed)

@bot.event
async def on_ready():
    await tree.sync()
    print(f"connecté : {bot.user}")

bot.run(TOKEN)

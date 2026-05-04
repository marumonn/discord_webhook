import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
from datetime import datetime
import pytz
import requests
import base64

load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', '0'))

OWNER = 'marumonn'
REPO = 'discord_webhook'
FILE_PATH = 'status.txt'

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)


# =========================
# GitHub操作
# =========================
def get_status():
    try:
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        url = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{FILE_PATH}"

        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()

        data = res.json()
        content = base64.b64decode(data['content']).decode().strip()
        return content

    except Exception as e:
        print(f"❌ get_status error: {e}")
        return "active"


def update_status(status, user):
    try:
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        url = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{FILE_PATH}"

        res = requests.get(url, headers=headers, timeout=10)

        if res.status_code == 200:
            sha = res.json()['sha']
        else:
            sha = None

        payload = {
            "message": f"update: {status} by {user}",
            "content": base64.b64encode(status.encode()).decode(),
            "committer": {"name": "bot", "email": "bot@example.com"}
        }

        if sha:
            payload["sha"] = sha

        requests.put(url, headers=headers, json=payload, timeout=10)

        print(f"✅ status updated: {status}")

    except Exception as e:
        print(f"❌ update_status error: {e}")
        raise


# =========================
# ボタンUI
# =========================
class DoneButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="終わったよ！", style=discord.ButtonStyle.green, emoji="✅")
    async def done(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.defer()

        try:
            update_status("done", interaction.user.name)

            button.disabled = True
            await interaction.message.edit(view=self)

            await interaction.followup.send(
                "完了を記録しました！👍",
                ephemeral=True
            )

            await interaction.channel.send(
                f"✅ {interaction.user.name} が完了しました！"
            )

        except Exception as e:
            await interaction.followup.send(f"エラー: {e}", ephemeral=True)


# =========================
# 定期通知
# =========================
@tasks.loop(minutes=30)
async def send_reminder():

    if CHANNEL_ID == 0:
        return

    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)

    try:
        channel = await bot.fetch_channel(CHANNEL_ID)
    except:
        return

    status = get_status()

    is_time = (now.hour >= 19 or now.hour < 5)

    if is_time and status == "active":

        embed = discord.Embed(
            title="🎮 クランバトル",
            description="終わりましたか？",
            color=discord.Color.blue(),
            timestamp=now
        )

        view = DoneButton()
        await channel.send(embed=embed, view=view)

        print("📤 reminder sent")

    else:
        print(f"skip: {now.hour}, status={status}")


# =========================
# 毎日リセット
# =========================
@tasks.loop(minutes=1)
async def reset_status():

    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)

    if now.hour == 5 and now.minute == 0:

        update_status("active", "system")

        if CHANNEL_ID != 0:
            try:
                channel = await bot.fetch_channel(CHANNEL_ID)
                await channel.send("🔄 デイリーリセットしました")
            except:
                pass

        print("🔄 reset done")


# =========================
# コマンド
# =========================
@bot.command()
async def status(ctx):
    s = get_status()

    embed = discord.Embed(
        title="📊 ステータス",
        description=f"`{s}`",
        color=discord.Color.green() if s == "active" else discord.Color.orange()
    )

    await ctx.send(embed=embed)


@bot.command()
async def help_cmd(ctx):
    await ctx.send("!status で状態確認できます")


# =========================
# 起動
# =========================
@bot.event
async def on_ready():
    print(f"✅ logged in: {bot.user}")

    if not send_reminder.is_running():
        send_reminder.start()

    if not reset_status.is_running():
        reset_status.start()


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
import subprocess
from datetime import datetime, time
import pytz

load_dotenv()

# 環境変数から取得
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', '0'))

OWNER = 'marumonn'
REPO = 'discord_webhook'
FILE_PATH = 'status.txt'

# Bot 設定
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
bot = commands.Bot(command_prefix='!', intents=intents)

# グローバル変数：今日の通知メッセージ ID
today_message_id = None


class DoneButton(discord.ui.View):
    """クランバトル完了ボタン"""
    
    def __init__(self):
        super().__init__(timeout=None)  # タイムアウトなし
    
    @discord.ui.button(label='終わったよ！', style=discord.ButtonStyle.green, emoji='✅')
    async def done_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        try:
            await update_status('done', interaction.user.name)
            
            # ボタンを無効化
            button.disabled = True
            await interaction.message.edit(view=self)
            
            # ユーザーに通知
            await interaction.followup.send(
                f"{interaction.user.mention} クランバトル完了を報告しました！✅\n今日の通知は停止されました。",
                ephemeral=True
            )
            
            # チャンネルにも通知
            channel = interaction.channel
            await channel.send(f"✅ **{interaction.user.name}** さんがクランバトル終了を報告しました。")
            
        except Exception as e:
            await interaction.followup.send(f"❌ エラーが発生しました: {str(e)}", ephemeral=True)
            print(f"Error in done_button: {e}")


async def update_status(status, user):
    """GitHub の status.txt を更新"""
    try:
        # git clone
        clone_cmd = f'git clone https://{GITHUB_TOKEN}@github.com/{OWNER}/{REPO}.git /tmp/repo_{user}'
        subprocess.run(clone_cmd, shell=True, check=True, capture_output=True)
        
        # status.txt 更新
        update_cmd = f'echo "{status}" > /tmp/repo_{user}/{FILE_PATH}'
        subprocess.run(update_cmd, shell=True, check=True, capture_output=True)
        
        # git 設定
        git_config = f'cd /tmp/repo_{user} && git config user.name "discord-bot" && git config user.email "bot@discord.local"'
        subprocess.run(git_config, shell=True, check=True, capture_output=True)
        
        # git add
        git_add = f'cd /tmp/repo_{user} && git add {FILE_PATH}'
        subprocess.run(git_add, shell=True, check=True, capture_output=True)
        
        # git commit
        git_commit = f'cd /tmp/repo_{user} && git commit -m "Status updated to {status} by {user} via Discord"'
        subprocess.run(git_commit, shell=True, check=True, capture_output=True)
        
        # git push
        git_push = f'cd /tmp/repo_{user} && git push'
        subprocess.run(git_push, shell=True, check=True, capture_output=True)
        
        print(f"✅ Status updated: {status} by {user} at {datetime.now()}")
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Git command failed: {e}")
        raise Exception(f"GitHub 更新に失敗しました: {e.stderr.decode() if e.stderr else str(e)}")
    except Exception as e:
        print(f"❌ Error in update_status: {e}")
        raise


@tasks.loop(minutes=30)
async def send_reminder():
    """30分ごとに通知を送信（19:00～05:00 JST のみ）"""
    global today_message_id
    
    if CHANNEL_ID == 0:
        print("⚠️ CHANNEL_ID が設定されていません")
        return
    
    try:
        channel = bot.get_channel(CHANNEL_ID)
        if channel is None:
            print(f"⚠️ チャンネル {CHANNEL_ID} が見つかりません")
            return
        
        # 日本時間の時刻を取得
        jst = pytz.timezone('Asia/Tokyo')
        now_jst = datetime.now(jst)
        current_hour = now_jst.hour
        
        # status.txt を確認
        try:
            status_cmd = f'git show HEAD:{FILE_PATH}'
            result = subprocess.run(f'cd /tmp && git clone --depth 1 https://{GITHUB_TOKEN}@github.com/{OWNER}/{REPO}.git', 
                                  shell=True, capture_output=True)
            with open(f'/tmp/{REPO}/{FILE_PATH}', 'r') as f:
                status = f.read().strip()
        except:
            status = 'active'
        
        # 送信条件：19:00～05:00 かつ status が active
        IS_REMINDER_TIME = (current_hour >= 19 or current_hour < 5)
        
        if IS_REMINDER_TIME and status == 'active':
            embed = discord.Embed(
                title="🎮 クランバトル",
                description="クランバトルは終わりましたか？",
                color=discord.Color.blue(),
                timestamp=datetime.now(jst)
            )
            embed.add_field(
                name="報告方法",
                value="下のボタンをクリックして報告してください"
            )
            embed.set_footer(text="終了報告")
            
            view = DoneButton()
            message = await channel.send(embed=embed, view=view)
            today_message_id = message.id
            
            print(f"📤 Reminder sent at {now_jst.strftime('%Y-%m-%d %H:%M:%S JST')}")
        else:
            print(f"⏭️  Skip reminder (hour={current_hour}, status={status})")
            
    except Exception as e:
        print(f"❌ Error in send_reminder: {e}")


@tasks.loop(hours=24)
async def reset_status():
    """毎日 05:00 JST に status を 'active' にリセット"""
    try:
        jst = pytz.timezone('Asia/Tokyo')
        now_jst = datetime.now(jst)
        
        # 05:00 JST か確認
        if now_jst.hour == 5 and now_jst.minute < 5:
            await update_status('active', 'system')
            
            if CHANNEL_ID != 0:
                channel = bot.get_channel(CHANNEL_ID)
                if channel:
                    await channel.send("🔄 **デイリーリセット実行** - status.txt を 'active' にリセットしました。")
            
            print("✅ Daily reset completed")
            
    except Exception as e:
        print(f"❌ Error in reset_status: {e}")


@bot.event
async def on_ready():
    """Bot が起動したときの処理"""
    print(f'✅ Bot is ready! Logged in as {bot.user}')
    print(f'📌 Watching channel ID: {CHANNEL_ID}')
    
    # ループタスクを開始
    if not send_reminder.is_running():
        send_reminder.start()
    if not reset_status.is_running():
        reset_status.start()
    
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="クランバトル")
    )


@bot.command()
async def status(ctx):
    """現在の status.txt を確認"""
    try:
        await ctx.defer()
        
        # GitHub から status を取得
        get_status_cmd = f'cd /tmp && git clone --depth 1 https://{GITHUB_TOKEN}@github.com/{OWNER}/{REPO}.git temp_status'
        subprocess.run(get_status_cmd, shell=True, capture_output=True)
        
        with open('/tmp/temp_status/status.txt', 'r') as f:
            status_value = f.read().strip()
        
        embed = discord.Embed(
            title="📊 Status Check",
            description=f"**現在のステータス**: `{status_value}`",
            color=discord.Color.green() if status_value == 'active' else discord.Color.orange()
        )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")


@bot.command()
async def help_cmd(ctx):
    """ヘルプコマンド"""
    embed = discord.Embed(
        title="🤖 Bot コマンド一覧",
        color=discord.Color.purple()
    )
    embed.add_field(name="!status", value="現在のステータスを確認", inline=False)
    embed.add_field(name="!help_cmd", value="このメッセージを表示", inline=False)
    embed.add_field(name="ボタン", value="チャンネルの通知に表示されるボタンをクリック", inline=False)
    
    await ctx.send(embed=embed)


# Bot 起動
if __name__ == '__main__':
    if not DISCORD_TOKEN:
        print("❌ DISCORD_TOKEN が設定されていません")
        exit(1)
    
    bot.run(DISCORD_TOKEN)

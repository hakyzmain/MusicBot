import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
from datetime import datetime
import time
import subprocess
import sys

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='+', intents=intents, help_command=None)

OWNER_IDS = [первый дискорд айди, второй] // Владельцы бота (Нету задержек и тп)
LOG_CHANNEL_ID = айди канала // логи

ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'outtmpl': 'downloads/%(title)s.%(ext)s',
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'force_json': False,
    'no_check_certificate': True,
    'ignoreerrors': True,
    'logtostderr': False,
    'noplaylist': False,
    'extractaudio': True,
    'audioformat': 'mp3',
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'cookiefile': 'cookies.txt'
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin',
    'options': '-vn'
}

user_cooldowns = {}

class MusicBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues = {}
        self.current = {}
        self.playing_servers = set()
        self.bot_enabled = True
        self.searching_servers = set()
        self.last_activity = datetime.now()
        self.inactive_task = None
        self.ffmpeg_path = self.find_ffmpeg()
        self.volume_levels = {}
        self.repeat_modes = {}
        
    def find_ffmpeg(self):
        try:
            if sys.platform == "win32":
                result = subprocess.run(['where', 'ffmpeg'], capture_output=True, text=True, shell=True)
            else:
                result = subprocess.run(['which', 'ffmpeg'], capture_output=True, text=True)
            
            if result.returncode == 0:
                return result.stdout.strip().split('\n')[0]
            else:
                return 'ffmpeg'
        except:
            return 'ffmpeg'
    
    def get_queue(self, guild_id):
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]
    
    def get_repeat_mode(self, guild_id):
        return self.repeat_modes.get(guild_id, 'off')
    
    async def start_inactivity_check(self):
        self.inactive_task = self.bot.loop.create_task(self.check_inactivity())
    
    async def check_inactivity(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                time_since_activity = (datetime.now() - self.last_activity).total_seconds()
                
                if time_since_activity > 300 and self.bot_enabled and not self.playing_servers and not self.searching_servers:
                    voice_connected = any(guild.voice_client for guild in self.bot.guilds if guild.voice_client)
                    if not voice_connected:
                        await self.bot.change_presence(
                            status=discord.Status.idle,
                            activity=discord.Activity(type=discord.ActivityType.listening, name="ожидание запросов")
                        )
                
                await asyncio.sleep(30)
            except Exception as e:
                await self.log_error(f"Ошибка в проверке неактивности: {str(e)}")
                await asyncio.sleep(60)
    
    async def log_action(self, action, user, guild, details=""):
        try:
            log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                embed = discord.Embed(
                    title="Лог действий",
                    color=0x3498db,
                    timestamp=datetime.now()
                )
                embed.add_field(name="Действие", value=action, inline=True)
                embed.add_field(name="Пользователь", value=f"{user.name} ({user.id})", inline=True)
                embed.add_field(name="Сервер", value=f"{guild.name} ({guild.id})", inline=True)
                if details:
                    embed.add_field(name="Детали", value=details, inline=False)
                await log_channel.send(embed=embed)
        except Exception as e:
            print(f"Ошибка логирования: {e}")
    
    async def log_error(self, error_message):
        try:
            log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                embed = discord.Embed(
                    title="Ошибка бота",
                    color=0xff0000,
                    timestamp=datetime.now(),
                    description=error_message
                )
                await log_channel.send(embed=embed)
        except Exception as e:
            print(f"Ошибка логирования ошибки: {e}")
    
    async def update_presence(self):
        self.last_activity = datetime.now()
        
        if not self.bot_enabled:
            await self.bot.change_presence(status=discord.Status.dnd)
            return
        
        voice_connected = any(guild.voice_client for guild in self.bot.guilds if guild.voice_client)
        
        if self.playing_servers:
            playing_count = len(self.playing_servers)
            await self.bot.change_presence(
                status=discord.Status.online,
                activity=discord.Activity(type=discord.ActivityType.listening, name=f"музыку на {playing_count} серверах")
            )
        elif self.searching_servers:
            await self.bot.change_presence(
                status=discord.Status.online,
                activity=discord.Activity(type=discord.ActivityType.listening, name="поиск музыки...")
            )
        elif voice_connected:
            await self.bot.change_presence(
                status=discord.Status.online,
                activity=discord.Activity(type=discord.ActivityType.listening, name="готов к работе")
            )
        else:
            time_since_activity = (datetime.now() - self.last_activity).total_seconds()
            if time_since_activity > 300:
                await self.bot.change_presence(
                    status=discord.Status.idle,
                    activity=discord.Activity(type=discord.ActivityType.listening, name="ожидание запросов")
                )
            else:
                await self.bot.change_presence(
                    status=discord.Status.online,
                    activity=discord.Activity(type=discord.ActivityType.listening, name="готов к работе")
                )
    
    def play_next(self, ctx):
        guild_id = ctx.guild.id
        queue = self.get_queue(guild_id)
        repeat_mode = self.get_repeat_mode(guild_id)
        
        if repeat_mode == 'one' and self.current.get(guild_id):
            current_track = self.current[guild_id]
            self.play_track(ctx, current_track)
            return
        
        if len(queue) > 0:
            source = queue.pop(0)
            self.play_track(ctx, source)
        else:
            self.current[guild_id] = None
            self.playing_servers.discard(guild_id)
            asyncio.run_coroutine_threadsafe(self.update_presence(), self.bot.loop)
    
    def play_track(self, ctx, track_info):
        guild_id = ctx.guild.id
        self.current[guild_id] = track_info
        
        audio_source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(
                track_info['url'],
                executable=self.ffmpeg_path,
                **ffmpeg_options
            ),
            volume=self.volume_levels.get(guild_id, 0.5)
        )
        
        ctx.voice_client.play(audio_source, after=lambda e: self.play_next(ctx))
        
        track_source = "плейлист" if track_info.get('playlist_index') else "трек"
        track_info_text = f"{track_info['title']} ({track_source})"
        
        asyncio.run_coroutine_threadsafe(
            ctx.send(f'Сейчас играет: {track_info_text}'),
            self.bot.loop
        )
        asyncio.run_coroutine_threadsafe(self.update_presence(), self.bot.loop)

    def is_owner():
        async def predicate(ctx):
            return ctx.author.id in OWNER_IDS
        return commands.check(predicate)

    async def check_cooldown(self, ctx):
        if ctx.author.id in OWNER_IDS:
            return True
            
        current_time = time.time()
        if ctx.author.id in user_cooldowns:
            if current_time - user_cooldowns[ctx.author.id] < 5:
                await ctx.send("Пожалуйста, подождите 5 секунд перед следующим запросом")
                return False
        
        user_cooldowns[ctx.author.id] = current_time
        return True

    def is_url(self, string):
        return string.startswith(('http://', 'https://', 'www.'))

    async def search_track(self, query):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if self.is_url(query):
                    info = ydl.extract_info(query, download=False)
                    
                    if '_type' in info and info['_type'] == 'playlist':
                        tracks = []
                        for entry in info['entries']:
                            if entry:
                                tracks.append({
                                    'url': entry['url'],
                                    'title': entry['title'],
                                    'duration': entry.get('duration', 0),
                                    'webpage_url': entry.get('webpage_url', ''),
                                    'playlist_index': info['entries'].index(entry) + 1,
                                    'playlist_title': info.get('title', 'Плейлист')
                                })
                        return tracks
                    else:
                        return [{
                            'url': info['url'],
                            'title': info['title'],
                            'duration': info.get('duration', 0),
                            'webpage_url': info.get('webpage_url', '')
                        }]
                else:
                    info = ydl.extract_info(f"ytsearch:{query}", download=False)
                    if 'entries' in info and info['entries']:
                        return [{
                            'url': info['entries'][0]['url'],
                            'title': info['entries'][0]['title'],
                            'duration': info['entries'][0].get('duration', 0),
                            'webpage_url': info['entries'][0].get('webpage_url', '')
                        }]
                    else:
                        return None
        except Exception as e:
            if "DRM" in str(e):
                await self.log_error(f"DRM защита для '{query}': {str(e)}")
                return "drm_error"
            await self.log_error(f"Ошибка поиска трека '{query}': {str(e)}")
            return None

    @commands.command()
    async def join(self, ctx):
        if not self.bot_enabled:
            await ctx.send("Бот временно отключен владельцем")
            return
            
        if not await self.check_cooldown(ctx):
            return
            
        if ctx.author.voice:
            try:
                channel = ctx.author.voice.channel
                await channel.connect()
                await ctx.send(f'Подключился к {channel.name}')
                await self.log_action("Подключение к голосовому каналу", ctx.author, ctx.guild, f"Канал: {channel.name}")
                await self.update_presence()
            except Exception as e:
                error_msg = f'Ошибка подключения: {str(e)}'
                await ctx.send(error_msg)
                await self.log_error(error_msg)
        else:
            await ctx.send('Вы не в голосовом канале')

    @commands.command()
    async def leave(self, ctx):
        if not await self.check_cooldown(ctx):
            return
            
        if ctx.voice_client:
            guild_id = ctx.guild.id
            self.playing_servers.discard(guild_id)
            if guild_id in self.volume_levels:
                del self.volume_levels[guild_id]
            if guild_id in self.repeat_modes:
                del self.repeat_modes[guild_id]
            await ctx.voice_client.disconnect()
            await ctx.send('Отключился от канала')
            await self.update_presence()
            await self.log_action("Отключение от голосового канала", ctx.author, ctx.guild)
        else:
            await ctx.send('Бот не в голосовом канале')

    @commands.command()
    async def play(self, ctx, *, query=None):
        if not self.bot_enabled:
            await ctx.send("Бот временно отключен владельцем")
            return
            
        if query is None:
            await ctx.send("Укажите название трека или ссылку")
            return
            
        if not await self.check_cooldown(ctx):
            return
            
        if not ctx.author.voice:
            await ctx.send('Зайдите в голосовой канал')
            return
            
        if not ctx.voice_client:
            try:
                await ctx.author.voice.channel.connect()
                await self.log_action("Подключение к голосовому каналу", ctx.author, ctx.guild, f"Канал: {ctx.author.voice.channel.name}")
            except Exception as e:
                error_msg = f'Ошибка подключения: {str(e)}'
                await ctx.send(error_msg)
                await self.log_error(error_msg)
                return
            
        self.searching_servers.add(ctx.guild.id)
        await ctx.send(f"Поиск: {query}")
        await self.update_presence()
        
        try:
            tracks_info = await self.search_track(query)
            if not tracks_info:
                await ctx.send('Не удалось найти трек. Попробуйте другое название или ссылку.')
                return
            elif tracks_info == "drm_error":
                await ctx.send('Этот контент защищен DRM и не может быть воспроизведен.')
                return
                
            guild_id = ctx.guild.id
            queue = self.get_queue(guild_id)
            
            if len(tracks_info) > 1:
                for track in tracks_info:
                    queue.append(track)
                await ctx.send(f'Добавлено {len(tracks_info)} треков из плейлиста в очередь')
                await self.log_action("Добавление плейлиста в очередь", ctx.author, ctx.guild, f"Треков: {len(tracks_info)}")
            else:
                track_info = tracks_info[0]
                
                if ctx.voice_client.is_playing():
                    queue.append(track_info)
                    track_source = "плейлист" if track_info.get('playlist_index') else "трек"
                    await ctx.send(f'Добавлено в очередь: {track_info["title"]} ({track_source})')
                    await self.log_action("Добавление трека в очередь", ctx.author, ctx.guild, f"Трек: {track_info["title"]}")
                else:
                    self.current[guild_id] = track_info
                    self.playing_servers.add(guild_id)
                    
                    audio_source = discord.PCMVolumeTransformer(
                        discord.FFmpegPCMAudio(
                            track_info['url'],
                            executable=self.ffmpeg_path,
                            **ffmpeg_options
                        ),
                        volume=self.volume_levels.get(guild_id, 0.5)
                    )
                    
                    ctx.voice_client.play(audio_source, after=lambda e: self.play_next(ctx))
                    track_source = "плейлист" if track_info.get('playlist_index') else "трек"
                    await ctx.send(f'Сейчас играет: {track_info["title"]} ({track_source})')
                    await self.log_action("Воспроизведение трека", ctx.author, ctx.guild, f"Трек: {track_info["title"]}")
                    
        except Exception as e:
            error_msg = f'Произошла ошибка при воспроизведении: {str(e)}'
            await ctx.send('Ошибка при воспроизведении трека')
            await self.log_error(error_msg)
        finally:
            self.searching_servers.discard(ctx.guild.id)
            await self.update_presence()

    @commands.command()
    async def pause(self, ctx):
        if not await self.check_cooldown(ctx):
            return
            
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send('Пауза')
            await self.log_action("Пауза трека", ctx.author, ctx.guild)
        else:
            await ctx.send('Ничего не играет')

    @commands.command()
    async def resume(self, ctx):
        if not await self.check_cooldown(ctx):
            return
            
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send('Продолжаем')
            await self.log_action("Продолжение воспроизведения", ctx.author, ctx.guild)
        else:
            await ctx.send('Не на паузе')

    @commands.command()
    async def skip(self, ctx):
        if not await self.check_cooldown(ctx):
            return
            
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send('Пропущено')
            await self.log_action("Пропуск трека", ctx.author, ctx.guild)
        else:
            await ctx.send('Ничего не играет')

    @commands.command()
    async def queue(self, ctx):
        guild_id = ctx.guild.id
        queue = self.get_queue(guild_id)
        
        if len(queue) == 0 and (not ctx.voice_client or not ctx.voice_client.is_playing()):
            await ctx.send('Очередь пуста')
            return
            
        current = self.current.get(guild_id)
        queue_list = []
        
        if current and ctx.voice_client and ctx.voice_client.is_playing():
            track_source = "плейлист" if current.get('playlist_index') else "трек"
            queue_list.append(f"Сейчас: {current['title']} ({track_source})")
            
        for i, item in enumerate(queue, 1):
            track_source = "плейлист" if item.get('playlist_index') else "трек"
            queue_list.append(f"{i}. {item['title']} ({track_source})")
            
        embed = discord.Embed(title="Очередь воспроизведения", description='\n'.join(queue_list), color=0x00ff00)
        await ctx.send(embed=embed)

    @commands.command()
    async def clear(self, ctx):
        if not await self.check_cooldown(ctx):
            return
            
        guild_id = ctx.guild.id
        self.queues[guild_id] = []
        await ctx.send('Очередь очищена')
        await self.log_action("Очистка очереди", ctx.author, ctx.guild)

    @commands.command()
    async def now(self, ctx):
        guild_id = ctx.guild.id
        current = self.current.get(guild_id)
        
        if current and ctx.voice_client and ctx.voice_client.is_playing():
            track_source = "плейлист" if current.get('playlist_index') else "трек"
            embed = discord.Embed(title="Сейчас играет", description=f"{current['title']} ({track_source})", color=0x00ff00)
            await ctx.send(embed=embed)
        else:
            await ctx.send('Сейчас ничего не играет')

    @commands.command()
    async def volume(self, ctx, volume: int = None):
        if not await self.check_cooldown(ctx):
            return
            
        if volume is None:
            current_volume = int((self.volume_levels.get(ctx.guild.id, 0.5) * 100))
            await ctx.send(f'Текущая громкость: {current_volume}%')
            return
            
        if ctx.voice_client:
            if 0 <= volume <= 100:
                self.volume_levels[ctx.guild.id] = volume / 100
                
                if ctx.voice_client.source and hasattr(ctx.voice_client.source, 'volume'):
                    ctx.voice_client.source.volume = volume / 100
                
                await ctx.send(f'Громкость установлена на {volume}%')
                await self.log_action("Изменение громкости", ctx.author, ctx.guild, f"Громкость: {volume}%")
            else:
                await ctx.send('Громкость должна быть от 0 до 100')
        else:
            await ctx.send('Бот не в голосовом канале')

    @commands.command()
    async def repeat(self, ctx, mode: str = None):
        if not await self.check_cooldown(ctx):
            return
            
        guild_id = ctx.guild.id
        
        if mode is None:
            current_mode = self.get_repeat_mode(guild_id)
            await ctx.send(f'Текущий режим повтора: {current_mode}')
            return
            
        mode = mode.lower()
        if mode in ['off', 'one', 'all']:
            self.repeat_modes[guild_id] = mode
            mode_names = {'off': 'выключен', 'one': 'один трек', 'all': 'весь плейлист'}
            await ctx.send(f'Режим повтора установлен на: {mode_names[mode]}')
            await self.log_action("Изменение режима повтора", ctx.author, ctx.guild, f"Режим: {mode}")
        else:
            await ctx.send('Доступные режимы: off, one, all')

    @commands.command()
    async def search(self, ctx, *, query=None):
        if not self.bot_enabled:
            await ctx.send("Бот временно отключен владельцем")
            return
            
        if query is None:
            await ctx.send("Укажите название трека для поиска")
            return
            
        await ctx.send(f"Ищу: {query}")
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch5:{query}", download=False)
                
                if 'entries' in info and info['entries']:
                    results = []
                    for i, entry in enumerate(info['entries'][:5], 1):
                        if entry:
                            duration = entry.get('duration', 0)
                            if duration:
                                minutes = duration // 60
                                seconds = duration % 60
                                duration_str = f"{minutes}:{seconds:02d}"
                            else:
                                duration_str = "Неизвестно"
                            
                            results.append(f"{i}. {entry['title']} ({duration_str})")
                    
                    if results:
                        embed = discord.Embed(title="Результаты поиска", description='\n'.join(results), color=0x00ff00)
                        embed.set_footer(text="Используйте +play [номер] чтобы добавить трек")
                        await ctx.send(embed=embed)
                    else:
                        await ctx.send("Ничего не найдено")
                else:
                    await ctx.send("Ничего не найдено")
                    
        except Exception as e:
            await ctx.send("Ошибка при поиске")
            await self.log_error(f"Ошибка поиска '{query}': {str(e)}")

    @commands.command()
    async def help(self, ctx):
        embed = discord.Embed(title="Помощь по командам бота", color=0x00ff00)
        embed.add_field(name="+join", value="Подключиться к голосовому каналу", inline=False)
        embed.add_field(name="+leave", value="Покинуть голосовой канал", inline=False)
        embed.add_field(name="+play [название/ссылка]", value="Воспроизвести трек", inline=False)
        embed.add_field(name="+search [название]", value="Поиск треков", inline=False)
        embed.add_field(name="+pause", value="Поставить на паузу", inline=False)
        embed.add_field(name="+resume", value="Продолжить воспроизведение", inline=False)
        embed.add_field(name="+skip", value="Пропустить текущий трек", inline=False)
        embed.add_field(name="+queue", value="Показать очередь", inline=False)
        embed.add_field(name="+clear", value="Очистить очередь", inline=False)
        embed.add_field(name="+now", value="Текущий трек", inline=False)
        embed.add_field(name="+volume [0-100]", value="Изменение громкости", inline=False)
        embed.add_field(name="+repeat [off/one/all]", value="Режим повтора", inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    @is_owner()
    async def shutdown(self, ctx):
        await ctx.send("Выключаю бота...")
        await self.log_action("Выключение бота", ctx.author, ctx.guild)
        await self.bot.close()

    @commands.command()
    @is_owner()
    async def disable(self, ctx):
        self.bot_enabled = False
        for guild_id in list(self.playing_servers):
            voice_client = self.bot.get_guild(guild_id).voice_client
            if voice_client:
                voice_client.stop()
        self.playing_servers.clear()
        await self.update_presence()
        await ctx.send("Бот отключен")
        await self.log_action("Отключение бота", ctx.author, ctx.guild)

    @commands.command()
    @is_owner()
    async def enable(self, ctx):
        self.bot_enabled = True
        await self.update_presence()
        await ctx.send("Бот включен")
        await self.log_action("Включение бота", ctx.author, ctx.guild)

    @commands.command()
    @is_owner()
    async def status(self, ctx):
        embed = discord.Embed(title="Статус бота", color=0x00ff00)
        embed.add_field(name="Серверов с музыкой", value=len(self.playing_servers), inline=True)
        embed.add_field(name="Всего серверов", value=len(self.bot.guilds), inline=True)
        embed.add_field(name="Статус бота", value="Включен" if self.bot_enabled else "Отключен", inline=True)
        embed.add_field(name="Путь к FFmpeg", value=self.ffmpeg_path, inline=False)
        embed.add_field(name="Последняя активность", value=self.last_activity.strftime("%Y-%m-%d %H:%M:%S"), inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    @is_owner()
    async def logs(self, ctx):
        embed = discord.Embed(title="Информация о логах", color=0x00ff00)
        embed.add_field(name="Канал логов", value=f"ID: {LOG_CHANNEL_ID}", inline=True)
        log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            embed.add_field(name="Статус", value="Канал доступен", inline=True)
        else:
            embed.add_field(name="Статус", value="Канал не найден", inline=True)
        await ctx.send(embed=embed)

    @commands.command()
    @is_owner()
    async def setffmpeg(self, ctx, path: str):
        self.ffmpeg_path = path
        await ctx.send(f"Путь к FFmpeg установлен: {path}")
        await self.log_action("Изменение пути к FFmpeg", ctx.author, ctx.guild, f"Новый путь: {path}")

async def setup_bot():
    await bot.add_cog(MusicBot(bot))

@bot.event
async def on_ready():
    await setup_bot()
    print(f'Бот {bot.user} готов к работе!')
    music_cog = bot.get_cog('MusicBot')
    await music_cog.update_presence()
    await music_cog.start_inactivity_check()

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    
    error_msg = f'Ошибка в команде {ctx.command}: {str(error)}'
    await ctx.send('Произошла ошибка при выполнении команды')
    
    music_cog = bot.get_cog('MusicBot')
    if music_cog:
        await music_cog.log_error(error_msg)

bot.run('токен discord developer portal') // https://discord.com/developers/applications/
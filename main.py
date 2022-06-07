import os
from datetime import datetime

import asyncpg
import discord
from discord.ext import commands, tasks

from grade_status import getCourseData

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot('gn!', intents=intents)
bot.remove_command('help')

EMOJI_STATUS = {
    'ยังไม่มีนักศึกษาลงทะเบียน': '🔵',
    'รออาจารย์ส่งเกรด': '🔴',
    'รอคณะส่งเกรด': '🟡',
    'ส่งเกรดสมบูรณ์': '✅'
}

async def create_db_pool():
    """Creates database pool"""
    bot.db = await asyncpg.create_pool(dsn=DATABASE_URL)
    print("Database connected")


async def fetch_course_channels():
    """ fetch guild courses data from database """
    bot.course_channels = [ 
        dict(record)
        for record in await bot.db.fetch('''
            SELECT c.*, ARRAY_AGG(g.notify_text_ch) AS channels
            FROM courses c, courses_in_guild cg, guilds g
            WHERE cg.course_id = c.id AND g.id = cg.guild_id
            GROUP BY c.id
        ''')
    ]
    print(f"Current bot.course_channels={bot.course_channels}")


@bot.listen()
async def on_ready():
    """on_ready Action"""
    print('Logged on as {0}!'.format(bot.user.name))
    # init uptime
    bot.startdate = datetime.now()
    await fetch_course_channels()
    # init tasks
    notify.start()

    # set bot presence
    await bot.change_presence(activity=discord.Streaming(
        name='รายชื่อคนที่ติด F', url='https://www.youtube.com/watch?v=dQw4w9WgXcQ'))


@bot.command()
async def helps(ctx):
    """Returns list of commands"""
    await ctx.message.delete()
    desc = """
`gn!helps` — แสดงคำสั่งทั้งหมด

`gn!uptime` — แสดง uptime ของบอท

`gn!setnotify` — ตั้งค่าแชนแนลนั้นให้เป็นค่าเริ่มต้นสำหรับการส่งแจ้งเตือนการเปลี่ยนแปลงสถานะ

`gn!list` — แสดงรายการรายวิชาทั้งหมด

`gn!add <ปีการศึกษา> <เทอม> <รหัสวิชา(ไม่มีช่องว่าง)> <กลุ่มการเรียน>` — เพิ่มรายวิชาเข้าสู่รายการ

`gn!remove <id>` — ลบรายวิชาออกจากรายการ
    """
    embed = discord.Embed(title="🚀 คำสั่งทั้งหมด", description=desc, color=0x75e8ff)
    embed.set_footer(text="ขอให้สนุกกับการใช้งาน หากพบปัญหาในการใช้งานโปรดติดต่อ Custard#2161")
    await ctx.send(embed=embed)


@bot.command()
@commands.has_permissions(administrator=True)
async def setnotify(ctx):
    """Set notify channel to guilds table"""
    try:
        await ctx.message.delete()
        await bot.db.execute(
            'UPDATE guilds SET notify_text_ch=$2 WHERE id=$1', ctx.guild.id, ctx.channel.id)
        await fetch_course_channels()
        await ctx.send(f'✅ **Channel สำหรับประกาศข้อมูลเกรดของเซิร์ฟเวอร์ {ctx.guild.name} คือ**\n`{ctx.channel.name}`')
    except Exception as e:
        await ctx.send('''❌ **เกิดข้อผิดพลาดในการตั้งค่า Channel**''')
        print(e)


@bot.command()
async def uptime(ctx):
    """Returns uptime of this bot"""
    await ctx.message.delete()
    now = datetime.now()
    uptime = now - bot.startdate
    total_seconds = int(uptime.total_seconds())
    hours, remainder = divmod(total_seconds,60*60)
    minutes, seconds = divmod(remainder,60)
    await ctx.send(f'⌛ Uptime: {hours} ชั่วโมง, {minutes} นาที, {seconds} วินาที')


@bot.event
async def on_guild_join(guild):
    try:
        await bot.db.execute('''
            INSERT INTO guilds(id) VALUES($1)
        ''', guild.id)
        print(f'Add guild "{guild.name}" with id={guild.id} into database')
    except Exception as e:
        print(e)

    await fetch_course_channels()


@bot.command()
@commands.has_permissions(administrator=True)
async def add(ctx, *args):
    """Adds course to database"""
    try:
        await ctx.message.delete()
        # check argument numbers
        if len(args) != 4:
            raise Exception("invalid arguments")

        # assign arguments into variables
        acadyear = int(args[0])
        semester = int(args[1])
        course_code = str(args[2])
        sec = int(args[3])

        # call web scraping function to get course data
        res = getCourseData(acadyear, semester, course_code, sec)

        # course not found
        if res is None:
            await ctx.send(
                '❌ **ไม่พบข้อมูลรายวิชาที่เปิดสอน กรุณาตรวจสอบข้อมูลให้ถูกต้อง**'
            )
            return

        # if the course has been graded
        if res[5] == 'ส่งเกรดสมบูรณ์':
            await ctx.send(
                '**ไม่สามารถเพิ่มรายวิชาได้ เนื่องจากรายวิชาดังกล่าวเกรดออกแล้ว**😰'
            )
            return

        # check course exists in db
        course_id = await bot.db.fetchval(
            '''
            SELECT id FROM courses 
            WHERE acadyear=$1 AND semester=$2 AND course_code=$3 AND sec=$4
            ''',
            res[0], res[1], res[2], res[4]
        )

        if course_id is not None:
            # check the guild has this course
            is_exist_in_this_guild = await bot.db.fetchval(
                '''SELECT EXISTS(SELECT 1 FROM courses_in_guild WHERE guild_id=$1 AND course_id=$2)''', 
                ctx.guild.id, course_id
            )

            if is_exist_in_this_guild:
                await ctx.send('⚠ **รายวิชานี้อยู่ในรายการอยู่แล้ว**')
                return
            else:
                # insert course into guild
                await bot.db.execute(
                    '''INSERT INTO courses_in_guild(guild_id, course_id) VALUES($1, $2)''',
                    ctx.guild.id, course_id
                )
        else:
            # insert new course and return course id
            inserted_course_id = await bot.db.fetchval(
                '''
                INSERT INTO courses(
                    acadyear, semester, course_code, course_name, sec, status
                )
                VALUES($1, $2, $3, $4, $5, $6) RETURNING id
                ''', 
                res[0], res[1], res[2], res[3], res[4], res[5]
            )
            if inserted_course_id is not None:
                # insert to courses_in_guild
                await bot.db.execute(
                    '''INSERT INTO courses_in_guild(guild_id, course_id) VALUES($1, $2)''', 
                    ctx.guild.id, inserted_course_id
                )

    except Exception as e:
        await ctx.send('''⚠ **กรุณาป้อนคำสั่งให้ถูกต้องตามรูปแบบ ดังนี้**
`gn!add <ปีการศึกษา> <เทอม> <รหัสวิชา(ไม่มีช่องว่าง)> <กลุ่มการเรียน>`''')
        print(e)
        return

    await fetch_course_channels()

    msg = f'''✅ **เพิ่มรายวิชาใหม่สำเร็จ**

> {res[3]}(Section {sec})
> สถานะ: {EMOJI_STATUS[res[5]]} {res[5]}

หากมีการเปลี่ยนแปลงสถานะเกรดระบบจะแจ้งเตือนให้ท่านทราบ\nสามารถดูรายวิชาทั้งหมดได้โดยป้อนคำสั่ง `gn!list`'''
    await ctx.send(msg)


@bot.command()
@commands.has_permissions(administrator=True)
async def remove(ctx, *args):
    """Remove course from database by id"""
    try:
        await ctx.message.delete()

        if len(args) != 1:
            await ctx.send('''⚠ **กรุณาป้อนคำสั่งให้ถูกต้องตามรูปแบบ ดังนี้**
`gn!remove <id>`''')
            return

        course_id = int(args[0])
        guild_id = ctx.guild.id
        
        is_exist_in_this_guild = await bot.db.fetchval(
                '''SELECT EXISTS(SELECT True FROM courses_in_guild WHERE guild_id=$1 AND course_id=$2)''', 
                guild_id, course_id
            )

        if not is_exist_in_this_guild:
            await ctx.send(
                f'❌ **ไม่พบข้อมูลรายวิชา id={course_id} ในเซิร์ฟเวอร์นี้**'
            )
            return

        await bot.db.fetch('''
                    DELETE FROM courses_in_guild
                    WHERE course_id=$1 AND guild_id=$2
                ''', course_id, guild_id)
        await fetch_course_channels()
        await ctx.send(f'✅ **ลบรายวิชา id={course_id} ออกจากรายการสำเร็จ**')

    except Exception as e:
        await ctx.send('''❌ **เกิดข้อผิดพลาดในการลบข้อมูล**''')
        print(e)


@bot.command()
async def list(ctx):
    """Returns list of courses"""
    await ctx.message.delete()
    courses = [ 
        dict(record)
        for record in await bot.db.fetch('''
            SELECT c.id, c.course_name, c.sec, c.status 
            FROM courses c, courses_in_guild cg 
            WHERE cg.guild_id=$1 AND c.id=cg.course_id
        ''', ctx.guild.id)
    ]
    if len(courses) > 0:
        embed = embed_template("📃 รายวิชาทั้งหมด", """
สามารถ**เพิ่ม**รายวิชาได้โดยใช้คำสั่ง
`gn!add <ปีการศึกษา> <เทอม> <รหัสวิชา(ไม่มีช่องว่าง)> <กลุ่มการเรียน>`

สามารถ**ลบ**รายวิชาได้โดยใช้คำสั่ง
`gn!remove <id>`
""")
        for course in courses:
            embed.add_field(name=f"{course['course_name']}\n(Section {int(course['sec'])}) [id={course['id']}]", value=f"{EMOJI_STATUS[course['status']]} {course['status']}\n", inline=True)
      
        await ctx.send(embed=embed)
    else:
        await ctx.send("⚠ **ไม่พบรายการ**")


@tasks.loop(seconds=60)
async def notify():
    for course in bot.course_channels:
        # data scraping to get new course data
        new_data = getCourseData(course['acadyear'], course['semester'], course['course_code'], course['sec'])
        # check for new course status
        if new_data[5] != course['status']:
            # check course status is graded or not
            if new_data[5] == 'ส่งเกรดสมบูรณ์':
                # delete course from database
                await bot.db.execute('''
                    DELETE FROM courses
                    WHERE id=$1;
                ''', course['id'])
                desc = 'หายใจเข้าลึก ๆ แล้วเปิด reg ดูเลย 🎉'
            else:
                # update course status to database
                await bot.db.execute('''
                    UPDATE courses SET status=$1 WHERE id=$2;
                ''', new_data[5], course['id'])
                desc = 'รอนาน ๆ ก็อาจจะบั่นทอนหัวใจ~'

            # loop channels in this course
            for ch in course['channels']:
                channel = bot.get_channel(ch) # get channel from bot by id
                # create embed template 
                embed = embed_template("📢 แจ้งเตือนเกรด", desc)
                embed.add_field(name=f"{new_data[3]}\n(Section {int(new_data[4])}, {int(new_data[1])}/{int(new_data[0])})", value=f"{EMOJI_STATUS[new_data[5]]} {new_data[5]}\n", inline=True)
                embed.set_image(url="https://memegenerator.net/img/instances/41287629/-.jpg")

                await channel.send(embed=embed)

            # fetch data to update variables bot.course_channels
            await fetch_course_channels()


def embed_template(title=None, desc=None):
    embed = discord.Embed(title=title, description=desc, color=0xa73b24)
    embed.set_author(name="ผู้ประกาศเกรด", url="https://kku.world/grade-notify-invite", icon_url=bot.user.avatar_url)
    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/816632544623067166/982530028845793320/Monogram_Logo-01.png")
    embed.timestamp = datetime.utcnow()
    embed.set_footer(text="ข้อมูลสถานะเกรดล่าสุดจาก reg.kku.ac.th")

    return embed


TOKEN = os.environ.get("DISCORD_BOT_SECRET")
DATABASE_URL = os.environ.get("DATABASE_URL")
bot.loop.run_until_complete(create_db_pool())
bot.run(TOKEN)

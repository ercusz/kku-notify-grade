import json
import os
from datetime import datetime

import discord
from discord.ext import commands, tasks

from grade_status import getStatus


intents = discord.Intents.default()
intents.members = True

bot = commands.Bot('gs!', intents=intents)
f = open('data.json', encoding='utf-8')
courses = json.load(f)

emoji_status = {
    'ยังไม่มีนักศึกษาลงทะเบียน': '🔵',
    'รออาจารย์ส่งเกรด': '🔴',
    'รอคณะส่งเกรด': '🟡',
    'ส่งเกรดสมบูรณ์': '✅'
}


@bot.listen()
async def on_ready():
    print('Logged on as {0}!'.format(bot.user.name))
    global startdate
    startdate = datetime.now()
    notify.start()
    write_json.start()
    await bot.change_presence(activity=discord.Streaming(
        name='รายชื่อคนที่ติด F', url='https://www.youtube.com/watch?v=dQw4w9WgXcQ'))


@bot.command()
async def uptime(ctx):
    """Returns uptime of this bot"""
    await ctx.message.delete()
    now = datetime.now()
    uptime = now - startdate
    total_seconds = int(uptime.total_seconds())
    hours, remainder = divmod(total_seconds,60*60)
    minutes, seconds = divmod(remainder,60)
    await ctx.send(f'⌛ Uptime: {hours} ชั่วโมง, {minutes} นาที, {seconds} วินาที')


@bot.listen()
async def on_message(message):
    print('Message from {0.author}: {0.content}'.format(message))


@bot.command()
@commands.has_permissions(administrator=True)
async def add(ctx, *args):
    """Adds course to database"""
    try:
        await ctx.message.delete()
        if len(args) != 4:
            raise Exception("invalid arguments")

        acadyear = int(args[0])
        semester = int(args[1])
        course_code = str(args[2])
        sec = int(args[3])

        res = getStatus(acadyear, semester, course_code, sec)

        if res is None:
            await ctx.send(
                '❌ **ไม่พบข้อมูลรายวิชาที่เปิดสอน กรุณาตรวจสอบข้อมูลให้ถูกต้อง**'
            )
            return

        if res[5] == 'ส่งเกรดสมบูรณ์':
            await ctx.send(
                '**ไม่สามารถเพิ่มรายวิชาได้ เนื่องจากรายวิชาดังกล่าวเกรดออกแล้ว**😰'
            )
            return

        for course in courses:
            if course['acadyear'] == res[0] and course['semester'] == res[
                    1] and course['course_code'] == res[2] and course[
                        'sec'] == res[4]:
                await ctx.send('⚠ **รายวิชานี้อยู่ในรายการอยู่แล้ว**')
                return

        courses.append({
            'acadyear': res[0],
            'semester': res[1],
            'course_code': res[2],
            'course_name': res[3],
            'sec': res[4],
            'status': res[5]
        })

    except Exception as e:
        await ctx.send('''⚠ **กรุณาป้อนคำสั่งให้ถูกต้องตามรูปแบบ ดังนี้**
`gs!add <ปีการศึกษา> <เทอม> <รหัสวิชา(ไม่มีช่องว่าง)> <กลุ่มการเรียน>`''')
        print(e)
        return

    msg = f'''✅ **เพิ่มรายวิชาใหม่สำเร็จ**

> {res[3]}(Section {sec})
> สถานะ: {emoji_status[res[5]]} {res[5]}

หากมีการเปลี่ยนแปลงสถานะเกรดระบบจะแจ้งเตือนให้ท่านทราบ\nสามารถดูรายวิชาทั้งหมดได้โดยป้อนคำสั่ง `gs!list`'''
    await ctx.send(msg)


@bot.command()
async def list(ctx):
    """Returns list of courses"""
    await ctx.message.delete()
    if len(courses) > 0:
        embed = discord.Embed(title="รายวิชาทั้งหมด", description="สามารถเพิ่มรายวิชาได้โดยใช้คำสั่ง\n`gs!add <ปีการศึกษา> <เทอม> <รหัสวิชา(ไม่มีช่องว่าง)> <กลุ่มการเรียน>`", color=0xa73b24)
        embed.set_author(name="ผู้ประกาศเกรด", url="https://kku.world/grade-notify-invite", icon_url=bot.user.avatar_url)
        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/816632544623067166/982530028845793320/Monogram_Logo-01.png")
        for course in courses:
            embed.add_field(name=f"{course['course_name']}\n(Section {course['sec']})", value=f"{emoji_status[course['status']]} {course['status']}", inline=True)
        embed.timestamp = datetime.utcnow()
        embed.set_footer(text="ข้อมูลสถานะเกรดล่าสุดจาก reg.kku.ac.th")
      
        await ctx.send(embed=embed)
    else:
        await ctx.send("⚠ **ไม่พบรายการ**")


@tasks.loop(seconds=10)
async def notify():
    for course in courses:
        new_data = getStatus(course['acadyear'], course['semester'],
                             course['course_code'], course['sec'])
        if new_data[5] != course['status']:
            print(f"{new_data[5]}, {course['status']}")
            if new_data[5] == 'ส่งเกรดสมบูรณ์':
                courses.remove(course)
                desc = 'หายใจเข้าลึก ๆ แล้วเปิด reg ดูเลย'
            else:
                course['status'] = new_data[5]
                desc = 'รอนาน ๆ ก็อาจจะบั่นทอนหัวใจ~'

            for guild in bot.guilds:
                for channel in guild.text_channels:
                    if channel.name == 'grade-notify':
                        embed = discord.Embed(title="แจ้งเตือนเกรด 🎉", description=desc, color=0xa73b24)
                        embed.set_author(name="ผู้ประกาศเกรด", url="https://kku.world/grade-notify-invite", icon_url=bot.user.avatar_url)
                        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/816632544623067166/982530028845793320/Monogram_Logo-01.png")
                        embed.set_image(url="https://memegenerator.net/img/instances/41287629/-.jpg")
                        embed.add_field(name=f"{new_data[3]}(Section {new_data[4]})", value=f"{emoji_status[new_data[5]]} {new_data[5]}", inline=True)
                        embed.timestamp = datetime.utcnow()
                        embed.set_footer(text="ข้อมูลสถานะเกรดล่าสุดจาก reg.kku.ac.th")
      
                        await channel.send(embed=embed)


@tasks.loop(seconds=300)
async def write_json():
    with open("data.json", "w", encoding="utf8") as f:
        json.dump(courses, f, indent=4, ensure_ascii=False)
        print('courses saved!')


TOKEN = os.environ.get("DISCORD_BOT_SECRET")
bot.run(TOKEN)

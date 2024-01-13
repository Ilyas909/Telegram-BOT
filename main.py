import logging
from sqlalchemy import create_engine, Column, Integer, String, DateTime, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from dateutil import parser
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from apscheduler.triggers.cron import CronTrigger

# Установите ваш токен бота
TOKEN = '***********'

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Создание базы данных и сессии SQLAlchemy
Base = declarative_base()
engine = create_engine('sqlite:///notes.db', echo=True)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()


# Определение модели данных для таблицы заметок
class Note(Base):
    __tablename__ = 'notes'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    task = Column(String)
    created_at = Column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    due_date = Column(DateTime)


# Функция обработки команды /start
def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(
        'Привет! Этот бот поможет вам вести заметки. Используйте /add для добавления задачи.')


def helpp(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(
        'Примеры команд\nДобавление задачи\n/add\n2024-01-14 01:11\nзадача\n\nСписок задач\n/list\n\nУдаление задачи\n/del номер задачи\n\nИзменение задачи\n/edit\nномер задачи\nдата\nзадача')


# Функция для добавления задачи в базу данных
def add_task(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    task_text = ' '.join(context.args)

    if not task_text:
        update.message.reply_text('Пожалуйста, укажите текст задачи после команды /add.')
        return

    # Извлечение даты и времени из первой строки задачи
    try:
        try:
            due_date = parser.parse(str(task_text.split()[0]) + ' ' + str(task_text.split()[1]))
            # Оставшаяся часть текста после даты и времени
            task_text = ' '.join(task_text.split()[2:])
        except ValueError:
            due_date = parser.parse(str(task_text.split()[0]))
            # Оставшаяся часть текста после даты и времени
            task_text = ' '.join(task_text.split()[1:])
    except Exception as e:
        update.message.reply_text(
            'Ошибка при извлечении даты из задачи. Пожалуйста, укажите дату в корректном формате.')
        return

    new_task = Note(user_id=user_id, task=task_text, due_date=due_date)
    session.add(new_task)
    session.commit()

    update.message.reply_text('Задача добавлена успешно!')

    # Добавление задачи в планировщик для напоминания
    context.job_queue.run_once(
        remind_task,
        due_date.timestamp() - datetime.now().timestamp(),
        context={'user_id': user_id, 'task_text': task_text}
    )


# Функция для отображения списка задач
def list_tasks(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    tasks = session.query(Note).filter_by(user_id=user_id).all()

    if not tasks:
        update.message.reply_text('У вас нет задач.')
    else:
        task_list = '\n'.join([f"{task.id}. {task.task} - Дата выполнения: {task.due_date}" for task in tasks])
        update.message.reply_text(f'Ваши задачи:\n{task_list}')


# Функция для удаления задачи
def delete_task(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id

    # Проверка наличия аргумента (номера задачи) после команды
    if not context.args:
        update.message.reply_text('Пожалуйста, укажите номер задачи для удаления после команды /delete.')
        return

    task_number = int(context.args[0])  # Получаем номер задачи из аргументов

    # Получаем задачу из базы данных по номеру и пользователю
    task_to_delete = session.query(Note).filter_by(user_id=user_id, id=task_number).first()

    if not task_to_delete:
        update.message.reply_text('Задачи с указанным номером не существует или не принадлежит вам.')
    else:
        # Удаляем задачу из базы данных
        session.delete(task_to_delete)
        session.commit()
        update.message.reply_text(f'Задача №{task_number} удалена успешно.')


# Функция для изменения задачи
def edit_task(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id

    # Проверка наличия аргумента (номера задачи) после команды
    if len(context.args) < 2:
        update.message.reply_text('Пожалуйста, укажите номер задачи и новый текст задачи после команды /edit.')
        return

    task_number = int(context.args[0])  # Получаем номер задачи из аргументов
    new_task_text = ' '.join(context.args[1:])  # Получаем новый текст задачи из аргументов

    # Получаем задачу из базы данных по номеру и пользователю
    task_to_edit = session.query(Note).filter_by(user_id=user_id, id=task_number).first()

    try:
        try:
            due_date = parser.parse(str(new_task_text.split()[0]) + ' ' + str(new_task_text.split()[1]))
            new_task_text = ' '.join(new_task_text.split()[2:])
        except IndexError:
            due_date = parser.parse(str(new_task_text.split()[0]))
            new_task_text = ' '.join(new_task_text.split()[1:])
    except:
        due_date = False

    if not task_to_edit:
        update.message.reply_text('Задачи с указанным номером не существует или не принадлежит вам.')
    else:
        # Изменяем текст задачи и обновляем базу данных
        if due_date:
            task_to_edit.due_date = due_date
        if new_task_text:
            task_to_edit.task = new_task_text
        session.commit()
        update.message.reply_text(f'Задача №{task_number} успешно изменена.')


# Функция для напоминания о задаче
def remind_task(context: CallbackContext) -> None:
    user_id = context.job.context['user_id']
    task_text = context.job.context['task_text']
    context.bot.send_message(chat_id=user_id, text=f'Напоминаю о задаче: {task_text}')


def delete_old_tasks():
    current_time = datetime.now()
    tasks_to_delete = session.query(Note).filter(Note.due_date < current_time - timedelta(days=1)).all()

    for task in tasks_to_delete:
        session.delete(task)
    session.commit()


# Основная функция
def main() -> None:
    scheduler = BackgroundScheduler()
    scheduler.start()

    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", helpp))
    dp.add_handler(CommandHandler("add", add_task, pass_args=True))
    dp.add_handler(CommandHandler("list", list_tasks))
    dp.add_handler(CommandHandler("del", delete_task, pass_args=True))
    dp.add_handler(CommandHandler("edit", edit_task, pass_args=True))
    scheduler.add_job(delete_old_tasks, trigger=CronTrigger(hour=0, minute=0, second=0))

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()

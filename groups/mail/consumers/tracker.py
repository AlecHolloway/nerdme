import re
import logging

from email.charset import Charset as EMailCharset
from django.db import transaction
from django.db.models import Count
from html2text import html2text
from groups.models import Comment, group, groupList

logger = logging.getLogger(__name__)


def part_decode(message):
    charset = ("ascii", "ignore")
    email_charset = message.get_content_charset()
    if email_charset:
        charset = (EMailCharset(email_charset).input_charset,)

    body = message.get_payload(decode=True)
    return body.decode(*charset)


def message_find_mime(message, mime_type):
    for submessage in message.walk():
        if submessage.get_content_type() == mime_type:
            return submessage
    return None


def message_text(message):
    text_part = message_find_mime(message, "text/plain")
    if text_part is not None:
        return part_decode(text_part)

    html_part = message_find_mime(message, "text/html")
    if html_part is not None:
        return html2text(part_decode(html_part))

    # groups: find something smart to do when no text if found
    return ""


def format_group_title(format_string, message):
    return format_string.format(subject=message["subject"], author=message["from"])


DJANGO_groups_THREAD = re.compile(r"<thread-(\d+)@django-groups>")


def parse_references(group_list, references):
    related_messages = []
    answer_thread = None
    for related_message in references.split():
        logger.info("checking reference: %r", related_message)
        match = re.match(DJANGO_groups_THREAD, related_message)
        if match is None:
            related_messages.append(related_message)
            continue

        thread_id = int(match.group(1))
        new_answer_thread = group.objects.filter(group_list=group_list, pk=thread_id).first()
        if new_answer_thread is not None:
            answer_thread = new_answer_thread

    if answer_thread is None:
        logger.info("no answer thread found in references")
    else:
        logger.info("found an answer thread: %d", answer_thread)
    return related_messages, answer_thread


def insert_message(group_list, message, priority, group_title_format):
    if "message-id" not in message:
        logger.warning("missing message id, ignoring message")
        return

    if "from" not in message:
        logger.warning('missing "From" header, ignoring message')
        return

    if "subject" not in message:
        logger.warning('missing "Subject" header, ignoring message')
        return

    logger.info(
        "received message:\t"
        f"[Subject: {message['subject']}]\t"
        f"[Message-ID: {message['message-id']}]\t"
        f"[References: {message['references']}]\t"
        f"[To: {message['to']}]\t"
        f"[From: {message['from']}]"
    )

    # Due to limitations in MySQL wrt unique_together and TextField (grrr),
    # we must use a CharField rather than TextField for message_id.
    # In the unlikeley event that we get a VERY long inbound
    # message_id, truncate it to the max_length of a MySQL CharField.
    original_message_id = message["message-id"]
    message_id = (
        (original_message_id[:252] + "...")
        if len(original_message_id) > 255
        else original_message_id
    )
    message_from = message["from"]
    text = message_text(message)

    related_messages, answer_thread = parse_references(group_list, message.get("references", ""))

    # find the most relevant group to add a comment on.
    # among Groups in the selected group list, find the group having the
    # most email members the current message references
    best_group = (
        group.objects.filter(group_list=group_list, comment__email_message_id__in=related_messages)
        .annotate(num_members=Count("comment"))
        .order_by("-num_members")
        .only("id")
        .first()
    )

    # if no related comment is found but a thread message-id
    # (generated by django-groups) could be found, use it
    if best_group is None and answer_thread is not None:
        best_group = answer_thread

    with transaction.atomic():
        if best_group is None:
            best_group = group.objects.create(
                priority=priority,
                title=format_group_title(group_title_format, message),
                group_list=group_list,
            )
        logger.info("using group: %r", best_group)

        comment, comment_created = Comment.objects.get_or_create(
            group=best_group,
            email_message_id=message_id,
            defaults={"email_from": message_from, "body": text},
        )
        logger.info("created comment: %r", comment)


def tracker_consumer(
    producer, group=None, group_list_slug=None, priority=1, group_title_format="[MAIL] {subject}"
):
    group_list = groupList.objects.get(group__name=group, slug=group_list_slug)
    for message in producer:
        try:
            insert_message(group_list, message, priority, group_title_format)
        except Exception:
            # ignore exceptions during insertion, in order to avoid
            logger.exception("got exception while inserting message")
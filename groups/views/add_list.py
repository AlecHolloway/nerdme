from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils.text import slugify

from groups.forms import AddgroupListForm
from groups.utils import staff_check


@login_required
@user_passes_test(staff_check)
def add_list(request) -> HttpResponse:
    """Allow users to add a new groups list to the group they're in.
    """

    # Only staffers can add lists, regardless of groups_STAFF_USER setting.
    if not request.user.is_staff:
        raise PermissionDenied

    if request.POST:
        form = AddgroupListForm(request.user, request.POST)
        if form.is_valid():
            try:
                newlist = form.save(commit=False)
                newlist.slug = slugify(newlist.name, allow_unicode=True)
                newlist.save()
                messages.success(request, "A new list has been added.")
                return redirect("groups:lists")

            except IntegrityError:
                messages.warning(
                    request,
                    "There was a problem saving the new list. "
                    "Most likely a list with the same name in the same group already exists.",
                )
    else:
        if request.user.groups.all().count() == 1:
            # FIXME: Assuming first of user's groups here; better to prompt for group
            form = AddgroupListForm(request.user, initial={"group": request.user.groups.all()[0]})
        else:
            form = AddgroupListForm(request.user)

    context = {"form": form}

    return render(request, "groups/add_list.html", context)
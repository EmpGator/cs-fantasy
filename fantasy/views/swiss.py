from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect

from ..forms.swiss import SwissModuleForm
from ..models import SwissModule
from ..utils.table import print_balanced_columns


def swiss_predictions(request: HttpRequest, pk: int) -> HttpResponse:
    """Make or edit predictions for a Swiss module"""
    module = get_object_or_404(SwissModule, pk=pk, is_active=True)
    user = request.user

    form = None
    if request.method == "POST":
        form = SwissModuleForm(module, user, request.POST, prefix=f"module_{module.id}")
        if form.is_valid():
            form.save()
            messages.success(request, "Your predictions have been saved!")
            return redirect("swiss_predictions", pk=module.pk)

    context = module.get_template_context(user)

    return render(request, "fantasy/modules/swiss/predictions.html", context)

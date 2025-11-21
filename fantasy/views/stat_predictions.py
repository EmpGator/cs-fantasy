from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect

from fantasy.models.stat_predictions import StatPredictionsModule

from ..forms.stat_predictions import StatPredictionForm


def stat_predictions(request: HttpRequest, pk: int) -> HttpResponse:
    user = request.user
    module = get_object_or_404(StatPredictionsModule, pk=pk, is_active=True)

    prefix = f"module_{module.id}"
    form_kwargs = {"prefix": prefix}

    if request.method == "POST":
        form = StatPredictionForm(module, user, request.POST, **form_kwargs)
        if form.save():
            messages.success(request, "Your predictions have been saved!")
            return redirect("stat_predictions", pk=module.pk)
    else:
        form = StatPredictionForm(module, user, **form_kwargs)

    context = module.get_template_context(user)
    context["form"] = form

    return render(request, "fantasy/modules/statprediction/predictions.html", context)

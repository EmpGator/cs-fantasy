from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect

from ..models import Bracket
from ..forms.bracket import BracketPredictionForm


def bracket_predictions(request: HttpRequest, pk: int) -> HttpResponse:
    user = request.user
    module = get_object_or_404(Bracket, pk=pk, is_active=True)

    form_kwargs = {"bracket": module, "user": user}

    if request.method == "POST":
        form = BracketPredictionForm(request.POST, **form_kwargs)
        if form.save():
            messages.success(request, "Your bracket predictions have been saved!")
            return redirect("bracket_predictions", pk=module.pk)
    else:
        form = BracketPredictionForm(**form_kwargs)

    context = module.get_template_context(user, form)
    context["form"] = form

    return render(request, "fantasy/modules/bracket/predictions.html", context)

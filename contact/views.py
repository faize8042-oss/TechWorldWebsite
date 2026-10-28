
import logging

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.urls import reverse
from django_ratelimit.decorators import ratelimit

from .forms import ContactSubmissionForm


logger = logging.getLogger(__name__)


@ratelimit(key="ip", rate="5/h", method="POST", block=False)
def contact(request):
    """Accept a contact request and email a notification."""

    # Stop processing if this IP has exceeded the submission limit.
    if request.method == "POST" and getattr(request, "limited", False):
        messages.error(
            request,
            "You have submitted too many enquiries. "
            "Please try again later."
        )
        return redirect("contact:contact")

    if request.method == "POST":
        form = ContactSubmissionForm(request.POST, request.FILES)

        if form.is_valid():
            submission = form.save()

            subject = (
                f"New Codeventra Labs enquiry: "
                f"{submission.get_project_type_display()}"
            )

            body = (
                "A new contact request was submitted on Codeventra Labs.\n\n"
                f"Name: {submission.name}\n"
                f"Email: {submission.email}\n"
                f"Project type: {submission.get_project_type_display()}\n"
                f"Budget: {submission.get_budget_range_display()}\n\n"
                "Message:\n"
                f"{submission.message}\n\n"
                f"Submission ID: {submission.pk}\n"
                "Review this request in Django Admin."
            )

            try:
                send_mail(
                    subject=subject,
                    message=body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[settings.CONTACT_EMAIL],
                    fail_silently=False,
                )
            except Exception as exc:
                logger.warning(
                    "Contact notification email failed for submission %s (%s)",
                    submission.pk,
                    type(exc).__name__,
                )

                messages.warning(
                    request,
                    "Your request was saved, but email notification "
                    "could not be sent. Please do not submit it again."
                )
            else:
                messages.success(
                    request,
                    "Thank you! Your request has been submitted successfully."
                )

            return redirect(reverse("contact:contact"))

    else:
        form = ContactSubmissionForm()

    return render(
        request,
        "contact/contact.html",
        {"form": form},
    )

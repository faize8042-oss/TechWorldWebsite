
from django import forms

from .models import ContactSubmission


class ContactSubmissionForm(forms.ModelForm):
    class Meta:
        model = ContactSubmission
        fields = [
            "name",
            "email",
            "project_type",
            "budget_range",
            "message",
            "attachment",
        ]

        widgets = {
            "name": forms.TextInput(
                attrs={
                    "placeholder": "Your full name",
                    "autocomplete": "name",
                    "maxlength": 100,
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "placeholder": "you@example.com",
                    "autocomplete": "email",
                    "maxlength": 254,
                }
            ),
            "project_type": forms.Select(),
            "budget_range": forms.Select(),
            "message": forms.Textarea(
                attrs={
                    "placeholder": (
                        "Tell us about your goals, requirements, "
                        "and what you would like to build."
                    ),
                    "rows": 6,
                    "maxlength": 5000,
                }
            ),
            "attachment": forms.ClearableFileInput(
                attrs={
                    "accept": ".pdf,.png,.jpg,.jpeg",
                }
            ),
        }

    def clean_name(self):
        name = self.cleaned_data["name"].strip()

        if not name:
            raise forms.ValidationError("Please enter your name.")

        return name

    def clean_message(self):
        message = self.cleaned_data["message"].strip()

        if not message:
            raise forms.ValidationError(
                "Please enter a message about your project."
            )

        return message

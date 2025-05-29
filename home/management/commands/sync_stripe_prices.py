import stripe
from django.core.management.base import BaseCommand
from transaction.models import Plan  # Replace 'your_app' with the actual app name
from django.conf import settings
from django.db import models

# Set your Stripe secret key
stripe.api_key = settings.PAYMENT_VARIANTS['stripe'][1]['secret_key']


class Command(BaseCommand):
    help = 'Sync Django plans with Stripe products and prices, and update stripe_price_id'

    def handle(self, *args, **kwargs):
        # Fetch all plans that need sync - either missing monthly or yearly price IDs
        plans = Plan.objects.filter(
            models.Q(stripe_price_id__isnull=True) | 
            models.Q(yearly_price__isnull=False, stripe_yearly_price_id__isnull=True)
        )

        for plan in plans:
            try:
                # Create or retrieve existing product in Stripe
                product_data = {
                    "name": plan.name,
                    "description": plan.description,
                }
                
                # Add features as metadata if available
                features_list = plan.features_as_list()
                if features_list:
                    product_data["metadata"] = {
                        f"feature_{i+1}": feature 
                        for i, feature in enumerate(features_list[:20])  # Stripe limits metadata
                    }
                    
                    # Add full features as a single metadata field if it doesn't exceed limit
                    if len(plan.features) <= 500:  # Stripe metadata value limit
                        product_data["metadata"]["features_full"] = plan.features
                
                # Create or update product
                if not hasattr(plan, '_stripe_product_id') or not plan._stripe_product_id:
                    product = stripe.Product.create(**product_data)
                    plan._stripe_product_id = product.id
                else:
                    product = stripe.Product.retrieve(plan._stripe_product_id)
                    stripe.Product.modify(plan._stripe_product_id, **product_data)
                
                # Create monthly price if needed
                if not plan.stripe_price_id:
                    monthly_price_data = {
                        "unit_amount": plan.get_total_cents(billing_cycle="monthly"),
                        "currency": "usd",
                        "recurring": {
                            "interval": "month",
                        },
                        "product": product.id,
                        "metadata": {
                            "plan_id": plan.id,
                            "billing_cycle": "monthly"
                        }
                    }
                    
                    # Add trial period if available
                    if plan.has_free_trial and plan.free_trial_days > 0:
                        monthly_price_data["recurring"]["trial_period_days"] = plan.free_trial_days
                    
                    monthly_price = stripe.Price.create(**monthly_price_data)
                    plan.stripe_price_id = monthly_price.id
                    self.stdout.write(self.style.SUCCESS(
                        f'Created monthly price for "{plan.name}" - {plan.price} USD/month'
                    ))
                
                # Create yearly price if needed and if yearly_price is set
                if plan.yearly_price is not None and not plan.stripe_yearly_price_id:
                    yearly_price_data = {
                        "unit_amount": plan.get_total_cents(billing_cycle="yearly"),
                        "currency": "usd",
                        "recurring": {
                            "interval": "year",
                        },
                        "product": product.id,
                        "metadata": {
                            "plan_id": plan.id,
                            "billing_cycle": "yearly"
                        }
                    }
                    
                    # Add trial period if available
                    if plan.has_free_trial and plan.free_trial_days > 0:
                        yearly_price_data["recurring"]["trial_period_days"] = plan.free_trial_days
                    
                    yearly_price = stripe.Price.create(**yearly_price_data)
                    plan.stripe_yearly_price_id = yearly_price.id
                    
                    # Include savings percentage in success message if applicable
                    savings_msg = ""
                    if plan.has_discount_for_yearly():
                        savings_msg = f" (saves {plan.get_yearly_savings_percentage()}%)"
                    
                    self.stdout.write(self.style.SUCCESS(
                        f'Created yearly price for "{plan.name}" - {plan.yearly_price} USD/year{savings_msg}'
                    ))
                
                # Save the plan with updated Stripe IDs
                plan.save()
                self.stdout.write(self.style.SUCCESS(
                    f'Successfully synced plan "{plan.name}" with Stripe'
                ))

            except Exception as e:
                self.stderr.write(self.style.ERROR(
                    f'Failed to sync plan "{plan.name}": {str(e)}'
                ))

from decimal import Decimal
from django.db import models
from django.urls import reverse
from django.contrib.auth import get_user_model

from payments import PurchasedItem
from payments.models import BasePayment

from utils.money import cents_to_dollar, dollar_to_cents

User = get_user_model()


class SUBSCRIPTION_STATUS(models.IntegerChoices):

    INACTIVE  = (0, 'inactive')
    ACTIVE  = (1, 'active')
    CANCELLED = (2, 'cancelled')
    PAST_DUE = (3, 'past due')
    ENDED = (4, 'ended')


# class Plan(models.Model):

#     name = models.CharField(max_length=150) # name of your plan
#     description = models.CharField(max_length=150) # small description of the plan

#     price = models.DecimalField(max_digits=9, decimal_places=2, default="0.0")

#     features = models.TextField(null=True, blank=True)

#     datetime = models.DateTimeField(auto_now=True)

#     def __str__(self) -> str:
#         return f'{self.name}'

#     def features_as_list(self):
        
#         if self.features:
#             return [x.strip() for x in self.features.split(",")]

#         return []
    
#     def get_total_cents(self):
#         # converts  dollar to cents.

#         return dollar_to_cents(self.price)


class Plan(models.Model):

    name = models.CharField(max_length=150) # name of your plan
    description = models.CharField(max_length=150) # small description of the plan

    price = models.DecimalField(max_digits=9, decimal_places=2, default="0.0", help_text="Monthly price in dollars")
    yearly_price = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True, help_text="Yearly price in dollars. If not set, will default to monthly price × 12")
    
    has_free_trial = models.BooleanField(default=False, help_text="Whether this plan offers a free trial")
    free_trial_days = models.PositiveIntegerField(default=0, help_text="Number of days for free trial period (if enabled)")
    
    stripe_price_id = models.CharField(max_length=255, null=True, blank=True)
    stripe_yearly_price_id = models.CharField(max_length=255, null=True, blank=True)

    features = models.TextField(null=True, blank=True)

    datetime = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.name}"

    def features_as_list(self):
        if self.features:
            return [x.strip() for x in self.features.split(",")]

        return []
    
    def get_total_cents(self, billing_cycle="monthly"):
        """
        Converts dollar to cents based on billing cycle.
        
        Args:
            billing_cycle: Either "monthly" or "yearly"
            
        Returns:
            int: Price in cents
        """
        if billing_cycle == "yearly":
            if self.yearly_price:
                return dollar_to_cents(self.yearly_price)
            else:
                # Default to monthly price × 12 if yearly price not set
                return dollar_to_cents(self.price * Decimal("12.0"))
        
        return dollar_to_cents(self.price)
    
    def get_effective_yearly_price(self):
        """
        Returns the yearly price or calculates it from monthly if not explicitly set.
        
        Returns:
            Decimal: Yearly price in dollars
        """
        if self.yearly_price:
            return self.yearly_price
        return self.price * Decimal("12.0")
    
    def has_discount_for_yearly(self):
        """
        Checks if there's a discount for paying yearly.
        
        Returns:
            bool: True if yearly price offers a discount compared to paying monthly
        """
        if not self.yearly_price:
            return False
        
        monthly_price_yearly = self.price * Decimal("12.0")
        return self.yearly_price < monthly_price_yearly
    
    def get_yearly_savings_percentage(self):
        """
        Calculates percentage saved by choosing yearly billing versus monthly.
        
        Returns:
            float: Percentage saved by choosing yearly billing, or 0 if no savings
        """
        if not self.has_discount_for_yearly():
            return 0
        
        monthly_yearly_total = self.price * Decimal("12.0")
        savings = monthly_yearly_total - self.yearly_price
        savings_percentage = (savings / monthly_yearly_total) * 100
        
        return round(float(savings_percentage), 1)



class Transaction(BasePayment):

    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    plan = models.ForeignKey(Plan, null=True, blank=True, on_delete=models.SET_NULL)

    subscription_id = models.CharField(max_length=255, null=True, blank=True) # creating stripe subscription
    customer_id = models.CharField(max_length=255, null=True, blank=True) # for creating stripe subscription

    subscription_status = models.PositiveSmallIntegerField(choices=SUBSCRIPTION_STATUS.choices, default=SUBSCRIPTION_STATUS.INACTIVE)

    subscription_item_id = models.CharField(max_length=255, blank=True, null=True)  # New field
    quantity = models.PositiveIntegerField(default=1)  # Add a quantity field

    def get_failure_url(self) -> str:
        # Return a URL where users are redirected after
        # they fail to complete a payment:
        return reverse('payment-failed')

    def get_success_url(self) -> str:
        # Return a URL where users are redirected after
        # they successfully complete a payment:
        return reverse('payment-success')


    def get_purchased_items(self):
        # Return items that will be included in this payment.

        yield PurchasedItem(
            name=self.plan.name,
            sku='none',
            quantity=self.quantity,
            price=self.plan.price,
            currency='USD',
        )

    def get_total_dollars(self):
        # converts  cents to dollars.

        total_cents = self.total
        return cents_to_dollar(total_cents)
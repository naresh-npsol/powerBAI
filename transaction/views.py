import stripe
from django.shortcuts import render
from django.conf import settings

from django.views.generic import View
from django.template.response import TemplateResponse
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

from payments import get_payment_model, RedirectNeeded
from django.urls import reverse

from .models import Plan, Transaction
from transaction.models import SUBSCRIPTION_STATUS  # Explicit import from transaction.models
from .forms import StripeSubscriptionForm

Payment = get_payment_model()
stripe.api_key = settings.PAYMENT_VARIANTS['stripe'][1]['secret_key']

def create_stripe_session(request):
    try:
        # Fetch the transaction for the authenticated user to get the customer ID
        transaction = Transaction.objects.get(user=request.user)

        # Check if the customer_id is available
        if not transaction.customer_id:
            # Set a specific session message for missing customer ID
            request.session['stripe_portal_error'] = "Stripe Customer ID not found for the transaction."
            return redirect(reverse('billing'))

        stripe_user_id = transaction.customer_id  # Get the customer ID from the transaction

        # Create a new Stripe session
        session = stripe.billing_portal.Session.create(
            customer=stripe_user_id,
            return_url="https://smartshorts.app/dashboard/billing"  # Redirect URL after session
        )
        # Redirect to the Stripe billing portal
        return redirect(session.url)

    except Transaction.DoesNotExist:
        # Set a specific session message for no transaction found
        request.session['stripe_portal_error'] = "No transaction found for the user."
        return redirect(reverse('billing'))
    except Exception as e:
        # Set a specific session message for the Stripe portal error
        request.session['stripe_portal_error'] = "Something went wrong while creating the Stripe session."
        return redirect(reverse('billing'))



@login_required
@require_http_methods(['POST'])
def create_payment(request):
    plan_id = request.POST.get("plan")
    quantity = request.POST.get("quantity", 1)  # Default to 1 if not provided
    billing_cycle = request.POST.get("billing_cycle", "monthly")  # Default to monthly
    
    try:
        plan = Plan.objects.get(id=int(plan_id))
        quantity = max(int(quantity), 1)  # Ensure quantity is a positive integer
        
        # Validate billing_cycle
        if billing_cycle not in ["monthly", "yearly"]:
            billing_cycle = "monthly"  # Default to monthly if invalid
            
    except (Plan.DoesNotExist, ValueError):
        return render(request, "404.html", status=404)

    currency = 'usd'
    
    # Select the right price ID and amount based on billing cycle
    if billing_cycle == "yearly" and plan.yearly_price is not None:
        stripe_price_id = plan.stripe_yearly_price_id
        plan_price = plan.yearly_price
    else:
        stripe_price_id = plan.stripe_price_id
        plan_price = plan.price

    try:
        # Check if the user already has an active subscription
        transaction = Transaction.objects.get(user=request.user, subscription_status=SUBSCRIPTION_STATUS.ACTIVE)
        
        # Determine current pricing based on transaction's billing cycle (assuming you've added this field)
        current_billing_cycle = getattr(transaction, 'billing_cycle', 'monthly')
        
        if current_billing_cycle == "yearly" and transaction.plan.yearly_price is not None:
            current_plan_price = transaction.plan.yearly_price
        else:
            current_plan_price = transaction.plan.price
            
        current_total_cost = current_plan_price * transaction.quantity
        new_total_cost = plan_price * quantity
        
        is_cycle_change = current_billing_cycle != billing_cycle
        
        if transaction.plan != plan or is_cycle_change:
            if new_total_cost > current_total_cost:
                # Upgrade: Immediate charge for upgrade
                stripe.Subscription.modify(
                    transaction.subscription_id,
                    items=[{
                        'id': transaction.subscription_item_id,
                        'price': stripe_price_id,
                        'quantity': quantity,
                    }],
                    proration_behavior='create_prorations'
                )

                invoice = stripe.Invoice.create(
                    customer=transaction.customer_id,
                    subscription=transaction.subscription_id,
                    auto_advance=True
                )

                transaction.plan = plan
                transaction.quantity = quantity
                if hasattr(transaction, 'billing_cycle'):
                    transaction.billing_cycle = billing_cycle
                transaction.save()

                billing_change_message = {
                    'status': 'Upgraded',
                    'new_plan': plan.name,
                    'new_quantity': quantity,
                    'new_billing_cycle': billing_cycle,
                    'invoice_id': invoice.id,
                    'message': f'Your plan has been upgraded to {plan.name} ({billing_cycle}) and charged immediately.'
                }

                # Store the message in session
                request.session['billing_change_messages'] = billing_change_message
                # Redirect to the billing page
                return redirect(reverse('billing'))

            elif new_total_cost < current_total_cost:
                # Downgrade: Credit applied to the next invoice
                stripe.Subscription.modify(
                    transaction.subscription_id,
                    items=[{
                        'id': transaction.subscription_item_id,
                        'price': stripe_price_id,
                        'quantity': quantity,
                    }],
                    proration_behavior='create_prorations'
                )

                transaction.plan = plan
                transaction.quantity = quantity
                if hasattr(transaction, 'billing_cycle'):
                    transaction.billing_cycle = billing_cycle
                transaction.save()

                billing_change_message = {
                    'status': 'Downgraded',
                    'new_plan': plan.name,
                    'new_quantity': quantity,
                    'new_billing_cycle': billing_cycle,
                    'message': f'Your plan has been downgraded to {plan.name} ({billing_cycle}). A credit will be applied to your next invoice.'
                }
            
                # Store the message in session
                request.session['billing_change_messages'] = billing_change_message
                # Redirect to the billing page
                return redirect(reverse('billing'))

        elif transaction.quantity != quantity:
            # Handle quantity change without plan change
            if quantity > transaction.quantity:
                # Quantity increase: Immediate charge
                stripe.SubscriptionItem.modify(
                    transaction.subscription_item_id,
                    quantity=quantity,
                    proration_behavior='create_prorations'
                )

                invoice = stripe.Invoice.create(
                    customer=transaction.customer_id,
                    subscription=transaction.subscription_id,
                    auto_advance=True
                )

                transaction.quantity = quantity
                transaction.save()

                billing_change_message = {
                    'status': 'Quantity Increased',
                    'new_quantity': quantity,
                    'invoice_id': invoice.id,
                    'message': 'Your subscription quantity has been increased and charged immediately.'
                }
            
                # Store the message in session
                request.session['billing_change_messages'] = billing_change_message
                # Redirect to the billing page
                return redirect(reverse('billing'))

            elif quantity < transaction.quantity:
                # Quantity decrease: Credit applied to next invoice
                stripe.SubscriptionItem.modify(
                    transaction.subscription_item_id,
                    quantity=quantity,
                    proration_behavior='create_prorations'
                )

                transaction.quantity = quantity
                transaction.save()

                billing_change_message = {
                    'status': 'quantity_decreased',
                    'new_quantity': quantity,
                    'message': 'Your subscription quantity has been decreased. A credit will be applied to your next invoice.'
                }

                # Store the message in session
                request.session['billing_change_messages'] = billing_change_message
                # Redirect to the billing page
                return redirect(reverse('billing'))

        billing_change_message = {'status': 'No Change', 'message': 'No changes were made to your subscription.'}
        # Store the message in session
        request.session['billing_change_messages'] = billing_change_message
        # Redirect to the billing page
        return redirect(reverse('billing'))
 
    except Transaction.DoesNotExist:
        # No active subscription, proceed to create a new one
        amount = plan_price * quantity

        payment = Payment.objects.create(
            variant='stripe',
            total=amount,
            currency=currency,
            description=plan.description or '',
            billing_email=request.user.email,
            user=request.user,
            plan=plan,
            quantity=quantity,
        )
        
        # If you've added the billing_cycle field to Transaction/Payment
        if hasattr(payment, 'billing_cycle'):
            payment.billing_cycle = billing_cycle

        pay_data = {
            'price': stripe_price_id,  # Use the appropriate Stripe Price ID based on billing cycle
            'quantity': quantity,
        }
        
        # Add free trial if applicable
        checkout_options = {
            'line_items': [pay_data],
            'mode': 'subscription',
            'success_url': request.build_absolute_uri(payment.get_success_url()),
            'cancel_url': request.build_absolute_uri(payment.get_failure_url()),
            'client_reference_id': request.user.id,
            'customer_email': request.user.email,
            'metadata': {
                'customer': request.user.id,
                'payment_id': payment.id,
                'billing_cycle': billing_cycle
            }
        }

        # Add trial period if applicable
        if plan.has_free_trial and plan.free_trial_days > 0:
            # Check if the user has previously had any subscription
            has_previous_subscription = Transaction.objects.filter(
                user=request.user,
                subscription_status__in=[SUBSCRIPTION_STATUS.ACTIVE, SUBSCRIPTION_STATUS.CANCELLED, SUBSCRIPTION_STATUS.PAST_DUE, SUBSCRIPTION_STATUS.ENDED]
            ).exists()
            
            # Only add free trial if user hasn't had a subscription before
            if not has_previous_subscription:
                checkout_options["subscription_data"] = {
                    "trial_period_days": plan.free_trial_days
                }
            # If they've had a subscription, they don't get another trial

        # Create the checkout session
        checkout_session = stripe.checkout.Session.create(**checkout_options)

        payment.transaction_id = checkout_session.id
        payment.save()

        return redirect(checkout_session.url)


# @login_required
# def payment_details(request, payment_id):
#     payment = get_object_or_404(get_payment_model(), id=payment_id)
    
#     try:
#         form = payment.get_form(data=request.POST or None)
#     except RedirectNeeded as redirect_to:
#         return redirect(str(redirect_to))

#     return TemplateResponse(
#         request,
#         'html/payment/stripe.html',
#         {'form': form, 'payment': payment}
#     )


def pricing(request):
    # Fetch the user's active subscription if it exists and the user is authenticated
    if request.user.is_authenticated:
        try:
            active_subscription = Transaction.objects.get(
                user=request.user,
                subscription_status=SUBSCRIPTION_STATUS.ACTIVE  # 1 is the value for ACTIVE status
            )
        except Transaction.DoesNotExist:
            active_subscription = None  # Send null if no active subscription exists
    else:
        active_subscription = None  # No user is logged in

    # Get the plans to display
    plans = Plan.objects.all()

    context = {
        'plans': plans,
        'active_plan': active_subscription.plan if active_subscription else None,
    }
    return render(request, 'html/payment/pricing.html', context)


def payment_success(request):

    return render(request, "html/payment/success.html")


def payment_failed(request):

    return render(request, "html/payment/failure.html")
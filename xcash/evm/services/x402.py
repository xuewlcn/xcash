from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.utils import timezone
from web3 import Web3

from chains.models import Address
from chains.models import ChainType
from evm.intents import Eip3009Authorization
from evm.intents import build_x402_eip3009_facilitate_intent
from evm.models import EvmBroadcastTask
from evm.models import X402Facilitation
from evm.models import X402FacilitationStatus
from evm.services.idempotency import lock_evm_idempotency_key

MIN_AUTHORIZATION_VALIDITY_SECONDS = 60


@dataclass
class X402CreateResult:
    facilitation: X402Facilitation


class X402FacilitationService:
    @classmethod
    @db_transaction.atomic
    def create_and_schedule(
        cls,
        *,
        facilitator: Address,
        chain,
        crypto,
        authorization: Eip3009Authorization,
    ) -> X402CreateResult:
        if facilitator.chain_type != ChainType.EVM:
            raise ValidationError("facilitator must be EVM system address")

        min_valid_before = (
            int(timezone.now().timestamp()) + MIN_AUTHORIZATION_VALIDITY_SECONDS
        )
        if authorization.valid_before <= min_valid_before:
            raise ValueError("x402 authorization valid_before is too close")

        authorization_from = Web3.to_checksum_address(authorization.from_address)
        authorization_to = Web3.to_checksum_address(authorization.to)
        lock_evm_idempotency_key(
            namespace="x402",
            key=(
                f"{chain.pk}:{crypto.pk}:"
                f"{authorization_from}:{authorization.nonce.hex()}"
            ),
        )

        existing = (
            X402Facilitation.objects.select_for_update(of=("self",))
            .filter(
                chain=chain,
                crypto=crypto,
                authorization_from_address=authorization_from,
                authorization_nonce=authorization.nonce,
            )
            .exclude(
                status__in=(
                    X402FacilitationStatus.FAILED,
                    X402FacilitationStatus.DROPPED,
                ),
            )
            .first()
        )
        if existing is not None:
            if (
                existing.facilitator_address_id == facilitator.pk
                and Web3.to_checksum_address(existing.authorization_to_address)
                == authorization_to
                and int(existing.authorization_value_raw) == int(authorization.value)
                and existing.valid_after == authorization.valid_after
                and existing.valid_before == authorization.valid_before
                and bytes(existing.authorization_r) == bytes(authorization.r)
                and bytes(existing.authorization_s) == bytes(authorization.s)
                and existing.authorization_v == authorization.v
            ):
                return X402CreateResult(facilitation=existing)
            raise ValueError("x402 authorization nonce conflict")

        facilitation = X402Facilitation.objects.create(
            chain=chain,
            crypto=crypto,
            facilitator_address=facilitator,
            authorization_from_address=authorization_from,
            authorization_to_address=authorization_to,
            authorization_value_raw=authorization.value,
            valid_after=authorization.valid_after,
            valid_before=authorization.valid_before,
            authorization_nonce=authorization.nonce,
            authorization_v=authorization.v,
            authorization_r=authorization.r,
            authorization_s=authorization.s,
            status=X402FacilitationStatus.CREATED,
        )

        intent = build_x402_eip3009_facilitate_intent(
            address=facilitator,
            chain=chain,
            crypto=crypto,
            authorization=authorization,
        )
        evm_task = EvmBroadcastTask.schedule(intent)

        facilitation.broadcast_task = evm_task.base_task
        facilitation.status = X402FacilitationStatus.BROADCASTED
        facilitation.save(update_fields=["broadcast_task", "status", "updated_at"])

        return X402CreateResult(facilitation=facilitation)

import json
from math import ceil

from consts import MIN_BOX_VALUE, TX_FEE
from helpers.job_helpers import latest_pool_info, job_processor
from helpers.node_calls import tree_to_address, box_id_to_binary, sign_tx, current_height
from helpers.platform_functions import calculate_service_fee, get_pool_param_box
from logger import set_logger

logger = set_logger(__name__)


def make_terminal_link(url, text=None):
    if not text:
        text = url
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"


def process_withdraw_proxy_box(pool, box, latest_tx):
    box_id = box.get('boxId', 'unknown')
    transaction_id = box.get('transactionId', 'unknown')
    explorer_url = f"https://ergexplorer.com/boxes#{box_id}" if box_id != 'unknown' else None

    if "assets" not in box or not box["assets"]:
        if explorer_url:
            link = make_terminal_link(explorer_url, "Erg Explorer")
            logger.error(
                f"[Withdraw Proxy SUSD] Box has no assets.\n"
                f"- Transaction ID: {transaction_id}\n"
                f"- Box ID: {box_id}\n"
                f"- Check the box on {link}\n"
                f"- If this persists, verify the bot's configuration or contact Duckpools support on Discord.\n"
            )
        else:
            logger.error(
                f"[Withdraw Proxy SUSD] Box has no assets.\n"
                f"- Transaction ID: {transaction_id}\n"
                f"- Box ID: unknown\n"
                f"- Unable to provide Erg Explorer link.\n"
                f"- Please verify the bot's configuration or contact Duckpools support on Discord.\n"
            )
        return None

    try:
        if box["assets"][0]["tokenId"] != pool["LEND_TOKEN"]:
            return latest_tx
        user_gives = box["assets"][0]["amount"]
    except (ValueError, TypeError) as e:
        link = make_terminal_link(explorer_url, "Erg Explorer") if explorer_url else "(no link)"
        logger.error(
            f"[Withdraw Proxy SUSD] Invalid asset amount: {e}.\n"
            f"- Transaction ID: {transaction_id}\n"
            f"- Box ID: {box_id}\n"
            f"- Check the box on {link}\n"
            f"- If this persists, contact Duckpools support on Discord.\n"
        )
        return None
    pool_box, borrowed = latest_pool_info(pool, latest_tx)

    held_erg0 = pool_box["assets"][3]["amount"]
    held_tokens = int(pool_box["assets"][1]["amount"])
    circulating_tokens = int(9000000000000010 - held_tokens)
    final_circulating = circulating_tokens - user_gives
    held_erg1 = ceil(final_circulating * (held_erg0 + borrowed) / circulating_tokens - borrowed) + 1
    total_entitled = held_erg0 - held_erg1
    service_fee = max(ceil(calculate_service_fee(total_entitled, pool["thresholds"])), 1)
    user_gets = total_entitled - service_fee
    user_tree = box["additionalRegisters"]["R4"]["renderedValue"]
    param_box = get_pool_param_box(pool["parameter"], pool["PARAMETER_NFT"])

    transaction_to_sign = \
        {
            "requests": [
                {
                    "address": pool["pool"],
                    "value": pool_box["value"],
                    "assets": [
                        {
                            "tokenId": pool_box["assets"][0]["tokenId"],
                            "amount": pool_box["assets"][0]["amount"]
                        },
                        {
                            "tokenId": pool_box["assets"][1]["tokenId"],
                            "amount": pool_box["assets"][1]["amount"] + user_gives
                        },
                        {
                            "tokenId": pool_box["assets"][2]["tokenId"],
                            "amount": pool_box["assets"][2]["amount"]
                        },
                        {
                            "tokenId": pool_box["assets"][3]["tokenId"],
                            "amount": pool_box["assets"][3]["amount"] - total_entitled
                        },
                    ],
                    "registers": {
                    }
                },
                {
                    "address": tree_to_address(param_box["additionalRegisters"]["R8"]["renderedValue"]),
                    "value": MIN_BOX_VALUE,
                    "assets": [
                        {
                            "tokenId": pool_box["assets"][3]["tokenId"],
                            "amount": service_fee
                        }
                    ],
                    "registers": {
                    }
                },
                {
                    "address": tree_to_address(user_tree),
                    "value": MIN_BOX_VALUE,
                    "assets": [
                        {
                            "tokenId": pool_box["assets"][3]["tokenId"],
                            "amount": user_gets
                        }
                    ],
                    "registers": {
                        "R4": "0500",
                        "R5": "0400",
                        "R6": "0400",
                        "R7": "0e20" + box["boxId"]
                    }
                }
            ],
            "fee": TX_FEE,
            "inputsRaw":
                [box_id_to_binary(pool_box["boxId"]), box_id_to_binary(box["boxId"])],
            "dataInputsRaw":
                [box_id_to_binary(param_box["boxId"])]
        }

    logger.debug("Signing Transaction: %s", json.dumps(transaction_to_sign))
    tx_id = sign_tx(transaction_to_sign)

    obj = {"txId": tx_id,
           "finalBorrowed": borrowed}
    if tx_id != -1:
        logger.info("Successfully submitted transaction with ID: %s", tx_id)
    else:
        logger.debug("Failed to submit transaction, attempting to refund")
        transaction_to_sign = \
            {
                "requests": [
                    {
                        "address": tree_to_address(user_tree),
                        "value": box["value"] - TX_FEE,
                        "assets": [
                            {
                                "tokenId": box["assets"][0]["tokenId"],
                                "amount": box["assets"][0]["amount"]
                            }
                        ],
                        "registers": {
                            "R4": "0e20" + box["boxId"]
                        }
                    }
                ],
                "fee": TX_FEE,
                "inputsRaw":
                    [box_id_to_binary(box["boxId"])],
                "dataInputsRaw":
                    []
            }

        logger.debug("Signing Transaction: %s",  json.dumps(transaction_to_sign))
        tx_id = sign_tx(transaction_to_sign)
        if tx_id != -1:
            logger.info("Successfully submitted refund transaction with ID: %s",  tx_id)
        else:
            logger.warning("Failed to process or refund transaction object: %s Failed Refund txID quoted as: %s",
                           json.dumps(transaction_to_sign), tx_id)
        return latest_tx
    return obj


def t_withdraw_proxy_job(pool, curr_tx_obj):
    return job_processor(pool, pool["proxy_withdraw"], curr_tx_obj, process_withdraw_proxy_box, "withdrawal", current_height() - 50)

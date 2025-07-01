import json

from consts import TX_FEE, MAX_BORROW_TOKENS
from helpers.job_helpers import latest_pool_info, job_processor
from helpers.node_calls import box_id_to_binary, sign_tx
from logger import set_logger

logger = set_logger(__name__)


def make_terminal_link(url, text=None):
    if not text:
        text = url
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"


def process_repay_to_pool_box(pool, box, latest_tx):
    erg_pool_box, borrowed = latest_pool_info(pool, latest_tx)
    erg_to_give = box["value"] - TX_FEE

    box_id = box.get('boxId', 'unknown')
    transaction_id = box.get('transactionId', 'unknown')
    explorer_url = f"https://ergexplorer.com/boxes#{box_id}" if box_id != 'unknown' else None

    if "assets" not in box or not box["assets"]:
        if explorer_url:
            link = make_terminal_link(explorer_url, "Erg Explorer")
            logger.error(
                f"[Repay to Pool] Box has no assets.\n"
                f"- Transaction ID: {transaction_id}\n"
                f"- Box ID: {box_id}\n"
                f"- Check the box on {link}\n"
                f"- If this persists, verify the bot's configuration or contact Duckpools support on Discord.\n"
            )
        else:
            logger.error(
                f"[Repay to Pool] Box has no assets.\n"
                f"- Transaction ID: {transaction_id}\n"
                f"- Box ID: unknown\n"
                f"- Unable to provide Erg Explorer link.\n"
                f"- Please verify the bot's configuration or contact Duckpools support on Discord.\n"
            )
        return None

    try:
        final_borrowed = borrowed - int(box["assets"][0]["amount"])
    except (ValueError, TypeError) as e:
        link = make_terminal_link(explorer_url, "Erg Explorer") if explorer_url else "(no link)"
        logger.error(
            f"[Repay to Pool] Invalid asset amount: {e}.\n"
            f"- Transaction ID: {transaction_id}\n"
            f"- Box ID: {box_id}\n"
            f"- Check the box on {link}\n"
            f"- If this persists, contact Duckpools support on Discord.\n"
        )
        return None

    transaction_to_sign = \
        {
            "requests": [
                {
                    "address": pool["pool"],
                    "value": erg_pool_box["value"] + erg_to_give,
                    "assets": [
                        {
                            "tokenId": erg_pool_box["assets"][0]["tokenId"],
                            "amount": erg_pool_box["assets"][0]["amount"]
                        },
                        {
                            "tokenId": erg_pool_box["assets"][1]["tokenId"],
                            "amount": erg_pool_box["assets"][1]["amount"]
                        },
                        {
                            "tokenId": erg_pool_box["assets"][2]["tokenId"],
                            "amount": MAX_BORROW_TOKENS - final_borrowed
                        }
                    ],
                    "registers": {
                    }
                },
            ],
            "fee": TX_FEE,
            "inputsRaw":
                [box_id_to_binary(erg_pool_box["boxId"]), box_id_to_binary(box["boxId"])],
            "dataInputsRaw":
                []
        }

    logger.debug("Signing Transaction: %s", json.dumps(transaction_to_sign))
    tx_id = sign_tx(transaction_to_sign)

    obj = {"txId": tx_id,
           "finalBorrowed": final_borrowed}
    if tx_id != -1:
        logger.info("Successfully submitted transaction with ID: %s", tx_id)
    else:
        logger.debug("Failed to submit transaction")
        return None
    return obj


def e_repay_to_pool_job(pool, curr_tx_obj):
    job_processor(pool, pool["repayment"], curr_tx_obj, process_repay_to_pool_box, "repay to pool", 1051829)

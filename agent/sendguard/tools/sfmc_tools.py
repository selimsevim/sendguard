"""Salesforce Marketing Cloud tools for SendGuard.

REST auth via client credentials (installed package, Server-to-Server).
All tools return dicts; errors come back as {"error": ...} so the agent can
narrate failures instead of crashing the demo.
"""

import os
import re
import time
from datetime import datetime, timezone

import requests

SUBDOMAIN = os.getenv("SFMC_SUBDOMAIN", "")
CLIENT_ID = os.getenv("SFMC_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("SFMC_CLIENT_SECRET", "")
ACCOUNT_ID = os.getenv("SFMC_ACCOUNT_ID", "")
SENDFLAG_DE_KEY = os.getenv("SFMC_SENDFLAG_DE_KEY") or "sendguard_flags"

AUTH_URL = f"https://{SUBDOMAIN}.auth.marketingcloudapis.com/v2/token"
REST_BASE = f"https://{SUBDOMAIN}.rest.marketingcloudapis.com"
SOAP_URL = f"https://{SUBDOMAIN}.soap.marketingcloudapis.com/Service.asmx"

_token_cache = {"token": None, "expires": 0.0}


def _token() -> str:
    if _token_cache["token"] and time.time() < _token_cache["expires"]:
        return _token_cache["token"]
    if not (SUBDOMAIN and CLIENT_ID and CLIENT_SECRET):
        raise RuntimeError("SFMC_SUBDOMAIN / SFMC_CLIENT_ID / SFMC_CLIENT_SECRET not configured")
    r = requests.post(AUTH_URL, timeout=30, json={
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "account_id": ACCOUNT_ID,
    })
    r.raise_for_status()
    d = r.json()
    _token_cache["token"] = d["access_token"]
    _token_cache["expires"] = time.time() + d.get("expires_in", 1200) - 60
    return _token_cache["token"]


def _soap_retrieve(object_type: str, properties: list[str], filter_xml: str = "") -> str:
    envelope = f"""<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
 xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing">
 <s:Header><a:Action s:mustUnderstand="1">Retrieve</a:Action>
  <a:To s:mustUnderstand="1">{SOAP_URL}</a:To>
  <fueloauth xmlns="http://exacttarget.com">{_token()}</fueloauth></s:Header>
 <s:Body><RetrieveRequestMsg xmlns="http://exacttarget.com/wsdl/partnerAPI">
  <RetrieveRequest><ObjectType>{object_type}</ObjectType>
   {''.join(f'<Properties>{p}</Properties>' for p in properties)}
   {filter_xml}
  </RetrieveRequest></RetrieveRequestMsg></s:Body></s:Envelope>"""
    r = requests.post(SOAP_URL, data=envelope.encode(), timeout=60,
                      headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "Retrieve"})
    r.raise_for_status()
    return r.text


def get_de_row_count(de_external_key: str) -> dict:
    """Get the current row count of an SFMC data extension.

    Args:
        de_external_key: the DE's external key (CustomerKey).

    Returns:
        dict with "row_count" and the DE key, or {"error": ...}.
    """
    try:
        r = requests.get(
            f"{REST_BASE}/data/v1/customobjectdata/key/{de_external_key}/rowset",
            params={"$pageSize": 1},
            headers={"Authorization": f"Bearer {_token()}"}, timeout=60)
        if r.status_code == 404:
            return {"error": f"Data extension with external key '{de_external_key}' not found"}
        r.raise_for_status()
        return {"de_external_key": de_external_key, "row_count": r.json().get("count")}
    except Exception as e:
        return {"error": f"SFMC row count failed for '{de_external_key}': {e}"}


def get_de_schema(de_external_key: str) -> dict:
    """Get the field schema (name, type, required, primary key) of an SFMC
    data extension by its external key."""
    try:
        flt = f"""<Filter xsi:type="SimpleFilterPart" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
          <Property>DataExtension.CustomerKey</Property>
          <SimpleOperator>equals</SimpleOperator>
          <Value>{de_external_key}</Value></Filter>"""
        xml = _soap_retrieve(
            "DataExtensionField",
            ["Name", "FieldType", "IsRequired", "IsPrimaryKey", "MaxLength"], flt)
        fields = []
        for m in re.finditer(
                r"<Results[^>]*>(.*?)</Results>", xml, re.S):
            blk = m.group(1)
            def grab(tag, b=blk):
                mm = re.search(f"<{tag}>(.*?)</{tag}>", b, re.S)
                return mm.group(1) if mm else None
            fields.append({"name": grab("Name"), "type": grab("FieldType"),
                           "required": grab("IsRequired"), "primary_key": grab("IsPrimaryKey")})
        if not fields:
            return {"error": f"No fields found for DE '{de_external_key}' (wrong key?)"}
        return {"de_external_key": de_external_key, "fields": fields}
    except Exception as e:
        return {"error": f"SFMC schema lookup failed for '{de_external_key}': {e}"}


def list_data_extensions() -> dict:
    """List data extensions in the account (name + external key)."""
    try:
        xml = _soap_retrieve("DataExtension", ["Name", "CustomerKey"])
        items = []
        for m in re.finditer(r"<Results[^>]*>(.*?)</Results>", xml, re.S):
            blk = m.group(1)
            name = re.search(r"<Name>(.*?)</Name>", blk, re.S)
            key = re.search(r"<CustomerKey>(.*?)</CustomerKey>", blk, re.S)
            items.append({"name": name.group(1) if name else None,
                          "external_key": key.group(1) if key else None})
        return {"data_extensions": items, "count": len(items)}
    except Exception as e:
        return {"error": f"SFMC DE listing failed: {e}"}


def _set_send_flag(campaign_id: str, status: str, reason: str) -> dict:
    try:
        r = requests.post(
            f"{REST_BASE}/hub/v1/dataevents/key:{SENDFLAG_DE_KEY}/rowset",
            headers={"Authorization": f"Bearer {_token()}"},
            json=[{
                "keys": {"campaign_id": campaign_id},
                "values": {"status": status, "reason": reason[:500],
                           "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")},
            }], timeout=60)
        r.raise_for_status()
        return {"campaign_id": campaign_id, "send_status": status, "reason": reason}
    except Exception as e:
        return {"error": f"Could not set send flag '{status}' for campaign '{campaign_id}': {e}. "
                         f"Check that DE '{SENDFLAG_DE_KEY}' exists with fields "
                         "campaign_id (PK), status, reason, updated_at."}


def hold_send(campaign_id: str, reason: str) -> dict:
    """HOLD a campaign send: writes status=HOLD to the SendGuard flag DE that
    gates the send automation. Use when validation fails or while repairing.

    Args:
        campaign_id: the campaign identifier.
        reason: plain-language explanation shown to the marketing team.
    """
    return _set_send_flag(campaign_id, "HOLD", reason)


def release_send(campaign_id: str, reason: str) -> dict:
    """RELEASE a campaign send: writes status=RELEASE to the SendGuard flag DE.
    Only call after validation passes AND a human has approved the release.

    Args:
        campaign_id: the campaign identifier.
        reason: plain-language summary of why the send is now safe.
    """
    return _set_send_flag(campaign_id, "RELEASE", reason)

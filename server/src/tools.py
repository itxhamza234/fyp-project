# tools.py
import asyncio
from datetime import datetime
from loguru import logger
from db_client import DBClient


def generate_complaint_number():
    """Generate unique complaint number: CMP-YYYYMMDD-XXXXX"""
    from uuid import uuid4
    unique_id = uuid4().hex[:5].upper()
    date_str = datetime.now().strftime("%Y%m%d")
    return f"CMP-{date_str}-{unique_id}"


def generate_meter_request_number():
    """Generate unique meter request number: MTR-YYYYMMDD-XXXXX"""
    from uuid import uuid4
    unique_id = uuid4().hex[:5].upper()
    date_str = datetime.now().strftime("%Y%m%d")
    return f"MTR-{date_str}-{unique_id}"


async def file_complaint_tool(
    chatbot_id: str,
    session_id: str,
    name: str,
    phone: str,
    cnic: str,
    area: str,
    address: str,
    complaint_type: str,
    complaint_description: str,
    reference_no: str = None,
) -> dict:
    """File a new complaint → store in DB → return complaint number"""
    db = DBClient()
    complaint_no = generate_complaint_number()

    complaint_data = {
        "complaint_no": complaint_no,
        "name": name,
        "phone": phone,
        "cnic": cnic,
        "reference_no": reference_no if reference_no else None,
        "area": area,
        "address": address,
        "complaint_type": complaint_type,
        "complaint_description": complaint_description,
        "status": "pending",
        "chatbot_id": chatbot_id,
        "session_id": session_id,
        "created_at": datetime.now().isoformat(),
    }

    try:
        # ✅ STORE IN DB — insert_one actually writes to MongoDB
        inserted_id = await db.create_complaint(complaint_data)

        if not inserted_id:
            logger.error("[COMPLAINT] insert_one returned no ID — save may have failed")
            return {
                "success": False,
                "message": "Shikayat save nahi ho saki. Please dobara koshish karein."
            }

        # ✅ VERIFY — read it back to confirm it really stored
        verified = await db.get_complaint_by_no(complaint_no)
        if not verified:
            logger.error(f"[COMPLAINT] Verification failed for {complaint_no}")
            return {
                "success": False,
                "message": "Shikayat save nahi ho saki. Please dobara koshish karein."
            }

        logger.info(f"[COMPLAINT] ✅ Stored & Verified | ID: {inserted_id} | No: {complaint_no}")

        return {
            "success": True,
            "complaint_no": complaint_no,
            "message": f"Aapki shikayat darj ho gayi hai. Aapka complaint number hai {complaint_no}. Please is number note kar lein."
        }

    except Exception as e:
        logger.error(f"[COMPLAINT] DB Error: {e}")
        return {
            "success": False,
            "message": "Database mein masla aaya. Shikayat save nahi ho saki. Please dobara koshish karein."
        }


async def check_complaint_status_tool(cnic: str, complaint_no: str) -> dict:
    """Check complaint status using CNIC and complaint number"""
    db = DBClient()

    try:
        complaint = await db.get_complaint_by_cnic_and_no(cnic, complaint_no)

        if not complaint:
            return {
                "success": False,
                "message": "Aapki shikayat nahi mili. Please CNIC aur complaint number dobara check karein."
            }

        status = complaint.get("status", "unknown")
        comp_type = complaint.get("complaint_type", "N/A")
        created = complaint.get("created_at", "N/A")

        # Build human-friendly status message
        status_urdu = {
            "pending": "under review mein hai",
            "in_progress": "process ho rahi hai",
            "resolved": "hal ho chuki hai",
            "rejected": "reject ho chuki hai",
        }
        status_text = status_urdu.get(status, status)

        msg = f"Aapki shikayat {complaint_no} ki type {comp_type} hai aur status {status_text} hai."
        if status == "resolved":
            msg += " Agar koi masla ho tou dobara contact karein."

        return {
            "success": True,
            "complaint_no": complaint_no,
            "complaint_type": comp_type,
            "status": status,
            "status_display": status_text,
            "created_at": created,
            "message": msg
        }

    except Exception as e:
        logger.error(f"[STATUS CHECK] DB Error: {e}")
        return {
            "success": False,
            "message": "Status check mein masla aaya. Please dobara koshish karein."
        }


async def request_new_meter_tool(
    chatbot_id: str,
    session_id: str,
    name: str,
    phone: str,
    cnic: str,
    area: str,
    address: str,
    meter_type: str,
    premises_type: str,
) -> dict:
    """Submit new meter connection request → store in DB → return request number"""
    db = DBClient()
    request_no = generate_meter_request_number()

    meter_data = {
        "request_no": request_no,
        "name": name,
        "phone": phone,
        "cnic": cnic,
        "area": area,
        "address": address,
        "meter_type": meter_type,
        "premises_type": premises_type,
        "status": "pending",
        "chatbot_id": chatbot_id,
        "session_id": session_id,
        "created_at": datetime.now().isoformat(),
    }

    try:
        # ✅ STORE IN DB
        inserted_id = await db.create_meter_request(meter_data)

        if not inserted_id:
            logger.error("[METER] insert_one returned no ID — save may have failed")
            return {
                "success": False,
                "message": "Meter request save nahi ho saki. Please dobara koshish karein."
            }

        # ✅ VERIFY — read it back
        verified = await db.get_meter_request_by_no(request_no)
        if not verified:
            logger.error(f"[METER] Verification failed for {request_no}")
            return {
                "success": False,
                "message": "Meter request save nahi ho saki. Please dobara koshish karein."
            }

        logger.info(f"[METER] ✅ Stored & Verified | ID: {inserted_id} | No: {request_no}")

        return {
            "success": True,
            "request_no": request_no,
            "message": f"Aapki meter request submit ho gayi hai. Aapka request number hai {request_no}. Please is number note kar lein."
        }

    except Exception as e:
        logger.error(f"[METER REQUEST] DB Error: {e}")
        return {
            "success": False,
            "message": "Database mein masla aaya. Meter request save nahi ho saki. Please dobara koshish karein."
        }


async def get_customer_info_tool(cnic: str) -> dict:
    """Get all complaints and meter requests for a customer by CNIC"""
    db = DBClient()

    try:
        complaints = await db.get_complaints_by_cnic(cnic)
        meter_requests = await db.get_meter_requests_by_cnic(cnic)

        if not complaints and not meter_requests:
            return {
                "success": False,
                "message": "Is CNIC par koi record nahi mila."
            }

        # Format for LLM response
        lines = []
        if complaints:
            lines.append(f"Total {len(complaints)} shikayatein milti hain:")
            for c in complaints[:5]:
                lines.append(
                    f"- {c.get('complaint_no')}: {c.get('complaint_type')} — Status: {c.get('status')}"
                )
        if meter_requests:
            lines.append(f"Total {len(meter_requests)} meter requests milti hain:")
            for r in meter_requests[:5]:
                lines.append(
                    f"- {r.get('request_no')}: {r.get('meter_type')} — Status: {r.get('status')}"
                )

        return {
            "success": True,
            "cnic": cnic,
            "complaints_count": len(complaints),
            "meter_requests_count": len(meter_requests),
            "formatted": "\n".join(lines),
            "message": "\n".join(lines)
        }

    except Exception as e:
        logger.error(f"[CUSTOMER INFO] DB Error: {e}")
        return {
            "success": False,
            "message": "Record dhoondhne mein masla aaya. Please dobara koshish karein."
        }


async def escalate_to_human_tool(
    session_id: str,
    reason: str,
    customer_name: str = None,
    customer_phone: str = None,
    customer_cnic: str = None,
) -> dict:
    """Escalate to human agent → store escalation in DB"""
    db = DBClient()

    escalation_data = {
        "session_id": session_id,
        "reason": reason,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "customer_cnic": customer_cnic,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
    }

    try:
        inserted_id = await db.create_escalation(escalation_data)

        if not inserted_id:
            logger.error("[ESCALATION] insert_one returned no ID")
            return {
                "success": False,
                "message": "Escalation save nahi ho saki."
            }

        logger.info(f"[ESCALATION] ✅ Stored | ID: {inserted_id} | Reason: {reason}")

        return {
            "success": True,
            "message": "Aapki call human agent ko transfer ho rahi hai. Please rukain, thori dair mein agent aayega."
        }

    except Exception as e:
        logger.error(f"[ESCALATION] DB Error: {e}")
        return {
            "success": False,
            "message": "Escalation mein masla aaya. Please rukain."
        }

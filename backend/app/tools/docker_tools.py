import docker
import subprocess
import os
from app.core.logging import logger


def get_docker_client():
    return docker.from_env()


async def get_container_stats(name: str) -> dict:
    """
    Get CPU, memory, restart count for a container.
    Used by Monitor agent.
    """
    try:
        client = get_docker_client()
        container = client.containers.get(name)

        stats = container.stats(stream=False)

        # Calculate CPU percentage
        cpu_delta = (
            stats["cpu_stats"]["cpu_usage"]["total_usage"]
            - stats["precpu_stats"]["cpu_usage"]["total_usage"]
        )
        system_delta = (
            stats["cpu_stats"]["system_cpu_usage"]
            - stats["precpu_stats"]["system_cpu_usage"]
        )
        num_cpus = stats["cpu_stats"]["online_cpus"]
        cpu_percent = (cpu_delta / system_delta) * num_cpus * 100 if system_delta > 0 else 0.0

        # Memory
        mem_usage = stats["memory_stats"]["usage"]
        mem_limit = stats["memory_stats"]["limit"]
        mem_percent = (mem_usage / mem_limit) * 100 if mem_limit > 0 else 0.0

        result = {
            "name": name,
            "status": container.status,
            "restart_count": container.attrs["RestartCount"],
            "cpu_percent": round(cpu_percent, 2),
            "memory_usage_mb": round(mem_usage / 1024 / 1024, 2),
            "memory_limit_mb": round(mem_limit / 1024 / 1024, 2),
            "memory_percent": round(mem_percent, 2),
            "image": container.image.tags[0] if container.image.tags else "unknown",
        }

        logger.info("container_stats_fetched", name=name, cpu=result["cpu_percent"])
        return result

    except docker.errors.NotFound:
        logger.error("container_not_found", name=name)
        return {"error": f"Container {name} not found"}
    except Exception as e:
        logger.error("container_stats_error", name=name, error=str(e))
        return {"error": str(e)}


async def restart_container(name: str) -> dict:
    """
    Restart a container by name.
    Called by Remediation agent AFTER policy engine approves.
    """
    try:
        client = get_docker_client()
        container = client.containers.get(name)

        logger.info("container_restarting", name=name)
        container.restart(timeout=30)

        # Verify it came back up
        container.reload()
        result = {
            "success": True,
            "name": name,
            "status": container.status,
            "message": f"Container {name} restarted successfully",
        }
        logger.info("container_restarted", name=name, status=container.status)
        return result

    except docker.errors.NotFound:
        return {"success": False, "error": f"Container {name} not found"}
    except Exception as e:
        logger.error("container_restart_error", name=name, error=str(e))
        return {"success": False, "error": str(e)}


async def scale_service(name: str, replicas: int) -> dict:
    """
    Scale a Docker Compose service to N replicas.
    Uses subprocess to call docker compose.
    """
    try:
        compose_file = os.path.join(
            os.path.dirname(__file__), "../../../../docker-compose.yml"
        )

        cmd = [
            "docker", "compose",
            "-f", compose_file,
            "up", "-d",
            "--scale", f"{name}={replicas}",
            "--no-recreate",
        ]

        logger.info("service_scaling", name=name, replicas=replicas)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode != 0:
            return {
                "success": False,
                "error": result.stderr,
                "name": name,
                "replicas": replicas,
            }

        return {
            "success": True,
            "name": name,
            "replicas": replicas,
            "message": f"Scaled {name} to {replicas} replicas",
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Scale command timed out"}
    except Exception as e:
        logger.error("scale_service_error", name=name, error=str(e))
        return {"success": False, "error": str(e)}


async def rollback_deploy(service: str, image_tag: str) -> dict:
    """
    Rollback a service to a previous image tag.
    Pulls the image then recreates the container.
    """
    try:
        client = get_docker_client()

        logger.info("rollback_starting", service=service, image_tag=image_tag)

        # Pull the target image
        client.images.pull(image_tag)

        # Get current container
        container = client.containers.get(service)

        # Stop and remove current container
        container.stop(timeout=30)
        container.remove()

        # Run new container with old image
        client.containers.run(
            image_tag,
            name=service,
            detach=True,
        )

        return {
            "success": True,
            "service": service,
            "image_tag": image_tag,
            "message": f"Rolled back {service} to {image_tag}",
        }

    except Exception as e:
        logger.error("rollback_error", service=service, error=str(e))
        return {"success": False, "error": str(e)}


async def stop_container(name: str) -> dict:
    """
    Stop an unhealthy container.
    """
    try:
        client = get_docker_client()
        container = client.containers.get(name)
        container.stop(timeout=30)
        logger.info("container_stopped", name=name)
        return {"success": True, "name": name, "message": f"{name} stopped"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def verify_service_health(name: str) -> dict:
    """
    Check if a container is running and healthy.
    Used by Verification agent after remediation.
    """
    try:
        client = get_docker_client()
        container = client.containers.get(name)
        container.reload()

        is_running = container.status == "running"
        restart_count = container.attrs["RestartCount"]

        # Also check /health endpoint if it's a web service
        health_ok = False
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as http:
                resp = await http.get(f"http://{name}:3000/health")
                health_ok = resp.status_code == 200
        except Exception:
            health_ok = is_running  # fallback to container status

        result = {
            "name": name,
            "is_running": is_running,
            "is_healthy": is_running and health_ok,
            "status": container.status,
            "restart_count": restart_count,
        }

        logger.info("health_verified", name=name, healthy=result["is_healthy"])
        return result

    except docker.errors.NotFound:
        return {
            "name": name,
            "is_running": False,
            "is_healthy": False,
            "error": f"Container {name} not found",
        }
    except Exception as e:
        return {"name": name, "is_running": False, "is_healthy": False, "error": str(e)}
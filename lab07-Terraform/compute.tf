locals {
  environment = {
    weather = {
      WEATHER_TABLE  = aws_dynamodb_table.weather.name
      CACHE_SECONDS  = var.cache_seconds
      NWS_USER_AGENT = "(itmo-444-544 weather lab, ${var.contact_email})"
    }

    advisor = {
      WEATHER_URL       = "http://${aws_lb.main.dns_name}:${local.tiers.weather.listener_port}"
      GEMINI_KEY_PARAM  = aws_ssm_parameter.gemini.name
      GEMINI_MODEL      = var.gemini_model
      KEY_CACHE_SECONDS = var.key_cache_seconds
    }
  }

  user_data = {
    for tier, _ in local.tiers : tier => templatefile("${path.module}/user-data.sh.tftpl", {
      service_name     = tier
      region           = var.aws_region
      app_js_b64       = base64encode(file("${path.module}/${tier}-app/app.js"))
      package_json_b64 = base64encode(file("${path.module}/${tier}-app/package.json"))
      environment      = local.environment[tier]
    })
  }
}

resource "aws_launch_template" "tier" {
  for_each = local.tiers

  name                   = "${var.name_prefix}-${each.key}-lt"
  image_id               = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  key_name               = var.key_name
  vpc_security_group_ids = [aws_security_group.app.id]
  user_data              = base64encode(local.user_data[each.key])
  update_default_version = true

  iam_instance_profile {
    name = aws_iam_instance_profile.tier[each.key].name
  }

  tag_specifications {
    resource_type = "instance"

    tags = {
      Name = "${each.key}-app"
    }
  }
}

resource "aws_autoscaling_group" "tier" {
  for_each = local.tiers

  name                      = "${var.name_prefix}-${each.key}-asg"
  min_size                  = 1
  max_size                  = 1
  desired_capacity          = 1
  vpc_zone_identifier       = data.aws_subnets.default.ids
  target_group_arns         = [aws_lb_target_group.tier[each.key].arn]
  health_check_type         = "ELB"
  health_check_grace_period = 120
  force_delete              = true

  launch_template {
    id      = aws_launch_template.tier[each.key].id
    version = aws_launch_template.tier[each.key].latest_version
  }

  instance_refresh {
    strategy = "Rolling"

    preferences {
      min_healthy_percentage = 0
    }
  }

  tag {
    key                 = "Name"
    value               = "${each.key}-app"
    propagate_at_launch = true
  }
}

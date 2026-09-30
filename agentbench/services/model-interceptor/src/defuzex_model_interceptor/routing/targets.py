"""Select configured destinations after protocol recognition and authentication."""
from ..error import TargetRoutingError


class ModelTargetRouter:
    def __init__(self, config, wires):
        self.config, self.wires = config, wires
        for rule in config.target_rules:
            for protocol in rule.protocols:
                if protocol not in wires:
                    raise TargetRoutingError(f'Unknown target-rule protocol: {protocol}')
                endpoints = config.targets[rule.target_id].endpoint_paths
                if endpoints is not None and wires[protocol]().endpoint not in endpoints:
                    raise TargetRoutingError(f'Target {rule.target_id} does not support {protocol}')

    def select(self, route, request):
        try:
            wire = self.wires[route.protocol_plugin]()
        except KeyError as exc:
            raise TargetRoutingError(f'Unknown model wire: {route.protocol_plugin}') from exc
        inspect = getattr(wire, 'requirements', None)
        if inspect is None:
            # Older external wire plugins retain text-generation compatibility.
            # Plugins supporting other operations/modalities must declare them.
            operation, modality = 'generation', 'text'
        else:
            operation, modality = inspect(request)
        if self.config.targets:
            matches = [rule for rule in self.config.target_rules
                       if route.protocol_plugin in rule.protocols and rule.input == modality]
            if len(matches) != 1:
                raise TargetRoutingError(f'No model target rule for {route.protocol_plugin}/{modality}')
            rule = matches[0]
            target, target_id, rule_id = self.config.targets[rule.target_id], rule.target_id, rule.rule_id
        else:
            if operation not in ('generation', 'token_count') or modality != 'text':
                raise TargetRoutingError(f'{operation}/{modality} requires an explicit target rule in ABB_MODEL_ROUTING_CONFIG')
            target, target_id, rule_id = self.config.target, 'default', 'legacy-text'
        if target is None or not {'text', modality}.issubset(target.input_modalities):
            raise TargetRoutingError(f'Target {target_id} does not support {modality} input')
        return target, target_id, rule_id, operation, modality

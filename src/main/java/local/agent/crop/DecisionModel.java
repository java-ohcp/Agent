package local.agent.crop;

import static local.agent.crop.Contracts.*;

@FunctionalInterface
public interface DecisionModel {
    ModelDecision decide(Perception.Context context) throws Exception;

    default ModelDecision repair(Perception.Context context, String validationFeedback) throws Exception {
        return decide(context);
    }
}

#pragma once

#include "CoreMinimal.h"
#include "ue5project/Scene/Task/TaskPointActor.h"
#include "PipelineLeakActor.generated.h"

UCLASS()
class UE5PROJECT_API APipelineLeakActor : public ATaskPointActor
{
	GENERATED_BODY()

public:
	APipelineLeakActor();

	virtual void InitTaskPoint(const FTaskPointInfo& InTaskPointInfo) override;
	
protected:
	virtual void BeginPlay() override;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly)
	UParticleSystemComponent* LeakParticle;
};

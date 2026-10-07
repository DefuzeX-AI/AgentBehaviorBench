#pragma once

#include "CoreMinimal.h"
#include "ue5project/Scene/Task/TaskPointActor.h"
#include "PollutionActor.generated.h"

UCLASS()
class UE5PROJECT_API APollutionActor : public ATaskPointActor
{
	GENERATED_BODY()

public:
	APollutionActor();
	
	virtual void InitTaskPoint(const FTaskPointInfo& InTaskPointInfo) override;

protected:
	virtual void BeginPlay() override;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly)
	UChildActorComponent* ChildActorComponent;
};

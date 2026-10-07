#pragma once

#include "CoreMinimal.h"
#include "TaskStruct.h"
#include "ue5project/Scene/EmbodiedIntelligence/EIActor.h"
#include "TaskPointActor.generated.h"

UCLASS()
class UE5PROJECT_API ATaskPointActor : public AEIActor
{
	GENERATED_BODY()

public:
	ATaskPointActor();

	virtual void InitTaskPoint(const FTaskPointInfo& InTaskPointInfo);
	FString GetTaskPointId() const;
	
protected:
	virtual void BeginPlay() override;
	FTaskPointInfo TaskPointInfo;
	

};

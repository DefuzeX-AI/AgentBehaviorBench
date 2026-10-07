#pragma once

#include "CoreMinimal.h"
#include "ue5project/Scene/Task/TaskPointActor.h"
#include "RescuePersonActor.generated.h"

class USphereComponent;

UCLASS()
class UE5PROJECT_API ARescuePersonActor: public ATaskPointActor
{
	GENERATED_BODY()

public:
	ARescuePersonActor();

protected:
	virtual void BeginPlay() override;
	
public:
	virtual void InitTaskPoint(const FTaskPointInfo& InTaskPointInfo) override;

protected:
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly)
	UChildActorComponent* ChildActorComponent;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly)
	USphereComponent* SphereComponent;
	
};

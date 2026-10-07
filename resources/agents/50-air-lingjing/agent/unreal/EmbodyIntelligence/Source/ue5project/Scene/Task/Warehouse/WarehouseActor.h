#pragma once

#include "CoreMinimal.h"
#include "ue5project/Scene/Task/TaskPointActor.h"
#include "WarehouseActor.generated.h"

UCLASS()
class UE5PROJECT_API AWarehouseActor : public ATaskPointActor
{
	GENERATED_BODY()

public:
	AWarehouseActor();

	virtual void InitTaskPoint(const FTaskPointInfo& InTaskPointInfo) override;

protected:
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly)
	UStaticMeshComponent* MarkerMesh;
	
};

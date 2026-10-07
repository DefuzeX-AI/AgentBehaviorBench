#pragma once

#include "CoreMinimal.h"
#include "CameraActorBase.h"
#include "EquipmentCameraActor.generated.h"


UCLASS()
class UE5PROJECT_API AEquipmentCameraActor : public ACameraActorBase
{
	GENERATED_BODY()

public:
	AEquipmentCameraActor();

protected:
	virtual void OnScrollUp() override;
	virtual void OnScrollDown() override;
};
